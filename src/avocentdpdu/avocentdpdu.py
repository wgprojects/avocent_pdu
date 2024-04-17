"""Module providing a Python interface to the Avocent PDU (e.g. DPDU101 DPDU10x DPDU20x) over HTTP"""

from enum import Enum
import logging as _LOGGER
import asyncio
import aiohttp

# Avocent PDU DPDU10x
# Tested on DPDU101
# Manual UI notes:
# Press and hold the key after:
#    1 beep; it can let the meter to show up the current information,
#      temperature and humidity in sequence.(by model)
#    2 beep; it can let the meter to show up the IP address
#    4 beep; it can change the way to get IP by DHCP or fixed IP.
#    6 beep; it can reset PDU back to default setting.


class Outlet():
    """Child class of an Avocent PDU representing a controllable outlet.
    Construct an AvocentDPDU and call .switches() to get a list of these objects.
    """
    name = "ERR: Not Found"

    def __init__(self, avocent_pdu: 'AvocentDPDU', outlet_idx: int, number_outlets: int, timeout: int):
        self.pdu = avocent_pdu
        self.outlet_idx = outlet_idx
        self.outlet_id = outlet_idx + 1
        self.is_on_bool = False
        self.timeout = timeout

        # e.g. 0100000 to control OutletB 
        # or 11111111 to control all outlets on an 8 port unit
        self.switch_flag = '0'*(outlet_idx) + '1' + '0'*(number_outlets-outlet_idx-1)

    async def obtain_name(self):
        """Call after initialization to obtain outlet name from PDU"""
        async with aiohttp.ClientSession() as session:
            async with session.get(f'http://{self.pdu.host}/switch{self.outlet_id}.cgi', timeout=self.timeout) as response:
                html = await response.text()
                if response.status == 200:
                    self.name = html.strip()
                else:
                    _LOGGER.warning("Could not find Avocent PDU outlet index %d at %s", self.outlet_idx, self.pdu.host)

    def is_on(self):
        """Returns boolean status of this outlet on=True"""
        return self.is_on_bool

    def is_on_string(self):
        """Returns status of this outlet as string On/Off"""
        return 'On' if self.is_on_bool else 'Off'

    def get_name(self):
        """Returns Avocent name for the outlet"""
        return self.name

    async def turn_on(self):
        """Command to turn outlet on"""
        _LOGGER.info('turn_on(%s)', self.name)
        await self.pdu.command_state(SwitchCommand.TURN_ON, self.switch_flag)

    async def turn_off(self):
        """Command to turn outlet off"""
        _LOGGER.info('turn_off(%s)', self.name)
        await self.pdu.command_state(SwitchCommand.TURN_OFF, self.switch_flag)

    def __repr__(self):
        return f'{self.name}: {self.is_on_string()}'


class SwitchCommand(Enum):
    """Enum used to command outlet to change status"""

    TURN_ON = 1
    TURN_OFF = 2


# Default Username 'snmp'
# Default Password '1234'
class AvocentDPDU():
    """Main class representing an Avocent PDU"""

    def __init__(self, host, username, password, timeout):
        _LOGGER.debug('Avocent PDU init')
        self.host = host
        self.username = username
        self.password = password
        self.number_outlets = -1
        self.password_status = "Not attempted"
        self.password_ok = False
        self.switch_list = []
        self.timeout = timeout
        self.pdu_status = "unknown"
        self.pdu_status_int = -1
        self.current_deciamps = 0
        self.password_status = "unknown"
        self.is_initialized = False
        self.mac = ""

    async def obtain_mac(self) -> str:
        """Get PDU's MAC address from index page"""
        async with aiohttp.ClientSession() as session:
            url = f'http://{self.host}/mac.cgi'
            async with session.get(url, timeout=self.timeout) as response:
                return await response.text()

    async def initialize(self) -> None:
        """Call once after construction to test login, and obtain Outlet names"""
        self.mac = await self.obtain_mac()  # Get MAC address identifier

        self.number_outlets = await self.query_num_outlets()
        assert self.number_outlets > 0

        _LOGGER.debug("PDU has %s outlets.", self.number_outlets)
        self.switch_list = [Outlet(self, N, self.number_outlets, self.timeout) for N in range(self.number_outlets)]

        # Pointless command used to test authentication (determined after an update())
        await self.command_state(SwitchCommand.TURN_OFF, "0"*self.number_outlets)

        # Request names for all outlets
        tasks = []
        for s in self.switch_list:
            tasks.append(s.obtain_name())
        await asyncio.gather(*tasks)

        self.is_initialized = True

        await self.update()
        _LOGGER.debug("PDU Authenticated: %s", self.is_valid_login())

    async def command_state(self, cmd_on: SwitchCommand, which_switches: str):
        """Command PDU to change one or more outlet states
        Note: The Avocent PDU commits the cardinal sin of using a GET request to change state
        """

        endpoint = '1' if cmd_on == SwitchCommand.TURN_ON else '3'

        async with aiohttp.ClientSession() as session:
            url = f'http://{self.host}/{endpoint}?3={self.username},{self.password},{which_switches},'
            async with session.get(url, timeout=self.timeout) as response:
                await response.text()
                # Response is always 404 with no body, even on success. Do nothing.

    async def query_num_outlets(self) -> int:
        """Check status and count number of reported outlet flags"""
        async with aiohttp.ClientSession() as session:
            url = f'http://{self.host}/control.cgi'
            async with session.get(url, timeout=self.timeout) as response:
                document = await response.text()
                if response.status == 200:
                    # Basic HTML parsing
                    if "Z1" in document:
                        name = document.split('name=')[1]
                        data2 = name.split(',')
                        statuses = data2[0]
                        return len(statuses)
        return -1

    async def update(self) -> None:
        """Get the status of the PDU"""

        if not self.is_initialized:
            await self.initialize()
            return

        async with aiohttp.ClientSession() as session:
            url = f'http://{self.host}/control.cgi'
            async with session.get(url, timeout=self.timeout) as response:
                document = await response.text()
                if response.status == 200:
                    # Basic HTML parsing
                    if "Z1" in document:
                        name = document.split('name=')[1]
                        _LOGGER.debug('Avocent Status = %s', name)
                        data2 = name.split(',')
                        statuses = data2[0]
                        self.current_deciamps = int(data2[1])
                        self.pdu_status_int = int(data2[2])
                        password_status = int(data2[3])

                        for N in range(self.number_outlets):
                            self.switch_list[N].is_on_bool = statuses[N] == '1'

                        if password_status == 2:
                            self.password_status = "Incorrect username or password"
                        elif password_status == 1:
                            self.password_status = "Login OK"
                        else:
                            self.password_status = "Login status unknown"

                        self.password_ok = True if password_status == 1 else False

                        self.pdu_status = "Normal" if self.pdu_status_int == 0 \
                            else "Warning!" if self.pdu_status_int == 1\
                            else "Overloading!"
        return

    def is_valid_login(self):
        """Returns True if the password was accepted at initialization"""
        return self.password_ok

    def switches(self):
        """Returns a list of outlets"""
        return self.switch_list

    def get_current_deciamps(self):
        """Returns the total current for the PDU in tenths of an ampere"""
        return self.current_deciamps

    def get_pdu_status_string(self):
        """Returns the PDU status string"""
        return self.pdu_status

    def get_pdu_status_integer(self):
        """Returns the PDU status integer"""
        return self.pdu_status_int

    def __repr__(self):
        switch_vals = ', '.join(map(repr, self.switch_list))
        return f"<AvocentPDU host:{self.host}; status:{self.pdu_status};\
        current:{self.current_deciamps/10.0}A;\
        login:{self.password_status}\n {switch_vals} >"


async def main():
    _LOGGER.basicConfig(level=_LOGGER.DEBUG)
    A = AvocentDPDU('192.168.1.131', 'snmp', '1234', 10)
    await A.initialize()
    # await A.update()
    print(A)

    # switches = A.switches()

    # switch = switches[2]
    # if switch.is_on():
    #     await switch.turn_off()
    # else:
    #     await switch.turn_on()

    # await A.update()
    # print(switch)

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
    loop.close()

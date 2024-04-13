"""Module providing a Python interface to the Avocent PDU (e.g. DPDU101 DPDU10x DPDU20x) over HTTP"""

from enum import Enum
import logging as _LOGGER
import requests


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
    Construct an AvocentPDU and call .switches() to get a list of these objects.
    """
    name = "ERR: Not Found"

    def __init__(self, avocent_pdu: 'AvocentPDU', outlet_idx: int, number_outlets: int):
        self.pdu = avocent_pdu
        outlet_id = outlet_idx + 1
        self.is_on_bool = False

        # e.g. 0100000 to control OutletB 
        # or 11111111 to control all outlets on an 8 port unit
        self.switch_flag = '0'*(outlet_idx) + '1' + '0'*(number_outlets-outlet_idx) 

        name_resp = requests.get(f'http://{self.pdu.host}/switch{outlet_id}.cgi', timeout=2)
        if name_resp.ok:
            self.name = name_resp.text.strip()
        else:
            _LOGGER.warning("Could not find Avocent PDU outlet index %d at %s", outlet_idx, self.pdu.host)

    def is_on(self):
        """Returns boolean status of this outlet on=True"""
        return self.is_on_bool

    def is_on_string(self):
        """Returns status of this outlet as string On/Off"""
        return 'On' if self.is_on_bool else 'Off'

    def turn_on(self):
        """Command to turn outlet on"""
        _LOGGER.info('turn_on(%s)', self.name)
        self.pdu.command_state(SwitchCommand.TURN_ON, self.switch_flag)

    def turn_off(self):
        """Command to turn outlet off"""
        _LOGGER.info('turn_off(%s)', self.name)
        self.pdu.command_state(SwitchCommand.TURN_OFF, self.switch_flag)

    def __repr__(self):
        return f'{self.name}: {self.is_on_string()}'


class SwitchCommand(Enum):
    """Enum used to command outlet to change status"""

    TURN_ON = 1
    TURN_OFF = 2


# Default Username 'snmp'
# Default Password '1234'
class AvocentPDU():
    """Main class representing an Avocent PDU"""

    def __init__(self, host, username, password, number_outlets):
        _LOGGER.info('Avocent PDU init')
        self.host = host
        self.username = username
        self.password = password
        self.number_outlets = number_outlets
        self.password_status = "Not attempted"
        self.password_ok = False
        self.switch_list = [Outlet(self, N, number_outlets) for N in range(self.number_outlets)]

        self.command_state(SwitchCommand.TURN_OFF, "0"*number_outlets)
        self.update()

    def command_state(self, cmd_on: SwitchCommand, which_switches: str):
        """Command PDU to change one or more outlet states
        Note: The Avocent PDU commits the cardinal sin of using a GET request to change state
        """

        endpoint = '1' if cmd_on == SwitchCommand.TURN_ON else '3'
        requests.get(f'http://{self.host}/{endpoint}?3={self.username},{self.password},{which_switches},', timeout=2)

    def update(self):
        """Get the status of the PDU"""
        ctrlResp = requests.get(f'http://{self.host}/control.cgi', timeout=2)
        if ctrlResp.ok:
            # Note: Unusual variable names were taken from Avocent Javascript
            document = ctrlResp.text
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
                    self.switch_list[N].is_on_bool = (statuses[N] == '1') 

                if password_status == 2:
                    self.password_status = "Incorrect username or password"
                elif password_status == 1:
                    self.password_status = "Login OK"
                else:
                    self.password_status = "Login status unknown"

                self.password_ok = True if password_status == 1 else False

                self.pdu_status = "Normal" if self.pdu_status_int == 0 else "Warning!" if self.pdu_status_int == 1 else "Overloading!"

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


if __name__ == "__main__":
    _LOGGER.basicConfig(level=_LOGGER.INFO)
    A = AvocentPDU('192.168.1.131', 'snmp', '1234', 8)
    print(A)

    switches = A.switches()

    # switch = switches[2]
    # if switch.is_on:
    #     switch.turn_off()
    # else:
    #     switch.turn_on()
    #
    # A.update()
    # print(switch)
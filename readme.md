Status and Control of Avocent PDU DPDU10x DPDU20x
Tested on DPDU101

# Manual UI notes:
# Press and hold the key after:
#    1 beep; it can let the meter to show up the current information,
#      temperature and humidity in sequence.(by model)
#    2 beep; it can let the meter to show up the IP address
#    4 beep; it can change the way to get IP by DHCP or fixed IP.
#    6 beep; it can reset PDU back to default setting.

Usage:

A = AvocentPDU('192.168.1.131', 'snmp', '1234', 8)
print(A)

switch = A.switches()[2]        # Select a switch/outlet
print(switch.name)              # Print the name given by Avocent
switch.turn_off()               # Command the outlet to turn off
A.update()                      # Status of all switches is only updated on update() and on initialization
print(A.get_current_deciamps()) # Total current (tenths of an ampere)
print(switch.is_on_string)      # Print the switch status
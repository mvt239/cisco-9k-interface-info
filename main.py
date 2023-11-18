import mysql.connector
import re
from pysnmp.hlapi import SnmpEngine, CommunityData, UdpTransportTarget, ContextData, ObjectType, ObjectIdentity, nextCmd
import sys

# good luck
def fetch_snmp_data(oid, target_ip, community_string):
    for errorIndication, errorStatus, errorIndex, varBinds in nextCmd(
        SnmpEngine(),
        CommunityData(community_string),
        UdpTransportTarget((target_ip, 161)),
        ContextData(),
        ObjectType(ObjectIdentity(oid)),
        lexicographicMode=False
    ):
        if errorIndication:
            print(errorIndication)
            break
        elif errorStatus:
            print('%s at %s' % (errorStatus.prettyPrint(),
                                errorIndex and varBinds[int(errorIndex) - 1][0] or '?'))
            break
        else:
            for varBind in varBinds:
                yield varBind

def sort_interfaces(interface_name):
    match = re.match(r"([a-zA-Z]+)([0-9]+)/([0-9]+)", interface_name)
    if match:
        return match.group(1), int(match.group(2)), int(match.group(3))
    else:
        return interface_name, 0, 0

def dns_friendly_name(interface_name, hostname):
    parts = re.match(r"([a-zA-Z]+)([0-9]+)/([0-9]+)", interface_name)
    if parts:
        friendly_name = parts.group(1).replace('Ethernet', 'eth-') + parts.group(2) + '-' + parts.group(3)
        return f"{friendly_name}.{hostname}"
    else:
        return f"{interface_name}.{hostname}"

def main():
    db_config = {
        'user': '',
        'password': '',
        'host': 'localhost',
        'database': '',
        'raise_on_warnings': True,
    }
# snmpv2 community string
    community_string = ''

#excluded interfaces... up to you
    excluded_interfaces = ['loopback', 'Loopback']
  
# iana interface types. Only built the ones I needed, add what you will. 
  iana_if_types = {
        '1': 'other',
        '6': 'ethernetCsmacd',
        '24': 'softwareLoopback',
        '49': 'FastEther',
        '161': 'ieee8023adLag',
        '53': 'propVirtual'
    }

    # Additional MIB OIDs
    mib_oids = {
        'ifMtu': '1.3.6.1.2.1.2.2.1.4',  # IF-MIB::ifMtu
        'ifType': '1.3.6.1.2.1.2.2.1.3',  # IF-MIB::ifType
        'ifSpeed': '1.3.6.1.2.1.2.2.1.5',  # IF-MIB::ifSpeed
        'ifAdminStatus': '1.3.6.1.2.1.2.2.1.7',  # IF-MIB::ifAdminStatus
        'ifOperStatus': '1.3.6.1.2.1.2.2.1.8',  # IF-MIB::ifOperStatus
    }

    # Modify the database insert query to include new columns
    upsert_query = """
    INSERT INTO interface_details (
        hostname, interface_name, ip_address, dns_entry, ifMtu, ifType, ifSpeed, ifAdminStatus, ifOperStatus)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
        ip_address = VALUES(ip_address),
        dns_entry = VALUES(dns_entry),
        ifMtu = VALUES(ifMtu),
        ifType = VALUES(ifType),
        ifSpeed = VALUES(ifSpeed),
        ifAdminStatus = VALUES(ifAdminStatus),
        ifOperStatus = VALUES(ifOperStatus)
    """

    try:
        cnx = mysql.connector.connect(**db_config)
        cursor = cnx.cursor(buffered=True)
        inner_cursor = cnx.cursor(buffered=True)  # Additional cursor for nested queries
        cursor.execute("SELECT COUNT(*) FROM host_inventory WHERE vendor ='Cisco'")
        total_hosts = cursor.fetchone()[0]

        query = ("SELECT ip_address, hostname FROM host_inventory WHERE vendor = 'Cisco'")
        cursor.execute(query)

        counter = 0
        for (host_ip, hostname) in cursor:
            counter += 1
            percent_complete = (counter / total_hosts) * 100
            print(f"Progress: {percent_complete:.2f}% completed", end='\r')
            sys.stdout.flush()

            interfaces = {str(varBind[0]).split('.')[-1]: str(varBind[1]) for varBind in fetch_snmp_data('1.3.6.1.2.1.2.2.1.2', host_ip, community_string)}
            ip_to_interface = {'.'.join(str(varBind[0]).split('.')[-4:]): str(varBind[1]) for varBind in fetch_snmp_data('1.3.6.1.2.1.4.20.1.2', host_ip, community_string)}

            # Fetch additional MIBs
            mib_values = {mib: {str(varBind[0]).split('.')[-1]: str(varBind[1]) for varBind in fetch_snmp_data(mib_oids[mib], host_ip, community_string)} for mib in mib_oids}

            data = []
            for ip, index in ip_to_interface.items():
                interface_name = interfaces.get(index, 'Unknown')
                if not any(interface_name.startswith(excluded) for excluded in excluded_interfaces):
                    dns_name = dns_friendly_name(interface_name, hostname)
                    mib_data = [mib_values[mib].get(index, 'Unknown') for mib in mib_oids]
                    # Translate ifType
                    if_type = mib_values['ifType'].get(index)
                    if_type_name = iana_if_types.get(if_type, 'Unknown')

                    # Replace the ifType in mib_data with the translated value
                    mib_data[list(mib_oids.keys()).index('ifType')] = if_type_name

                    op_status = mib_values['ifOperStatus'].get(index)
                    if op_status == '1':
                        op_status = 'up'
                    elif op_status == '2':
                        op_status = 'down'

                    # Replace the operational status in mib_data with the translated value
                    mib_data[list(mib_oids.keys()).index('ifOperStatus')] = op_status
                    data.append((hostname, interface_name, ip, dns_name) + tuple(mib_data))

            # Insert data into the database
            for record in data:
                try:
                    inner_cursor.execute(upsert_query, record)
                    cnx.commit()
                except mysql.connector.Error as err:
                    print(f"Error: {err}")
                    continue

    except mysql.connector.Error as err:
        print(f"error: {err}")
    finally:
        if cnx.is_connected():
            cursor.close()
            inner_cursor.close()
            cnx.close()

if __name__ == "__main__":
    main()

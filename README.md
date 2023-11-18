# cisco-9k-interface-info
A terrible script that scrapes a list of Cisco 9k's to pull interface/ip/mtu/oper/admin/etc information and inserts into a table. Includes a 'dns' friendly name that's used to update bind. 


List is fed via a MySQL table called 'host_inventory'. It's seeking 3 columns primarily: hostname, ip_address, vendor. It selects on vendor='Cisco'. The output of the script is inserted into `interface_details` with this schema:
```
id Primary	int(11)			No	None		AUTO_INCREMENT
2	  hostname
3	  interface_name
4	  ip_address
5	  dns_entry
6	  ifMtu
7  	ifType
8  	ifSpeed
9  	ifAdminStatus
10	ifOperStatus
```

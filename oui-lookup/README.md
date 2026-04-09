# SecureCRT OUI Lookup



Offline MAC vendor lookup for SecureCRT using the Wireshark `manuf` database.



## What it does



This script finds a MAC address from SecureCRT selected text, clipboard content, nearby screen text, or manual input.



It then:

- normalizes the MAC address

- looks up the OUI/vendor from `manuf.txt`

- prompts to run `show ip arp | inc <mac>` in the active SecureCRT tab



## Files



- `oui-lookup.py` - SecureCRT Python script

- `manuf.txt` - vendor/OUI database from Wireshark


\## Supported MAC formats



- `0011.2233.4455`

- `00:11:22:33:44:55`

- `00-11-22-33-44-55`

- `001122334455`



## Configuration



The script looks for `manuf.txt` in the same folder as `oui-lookup.py`.



## Usage



1. Highlight or copy a MAC address in SecureCRT

2. Run the script

3. Review the detected vendor

4. Optionally send the generated ARP command



## Data source



The `manuf.txt` file is sourced from Wireshark’s manufacturer database.



## Keywords



SecureCRT, OUI lookup, MAC vendor lookup, Wireshark manuf, ARP lookup, Cisco MAC lookup, network troubleshooting


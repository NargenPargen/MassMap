import logging, argparse, re, json, time, subprocess
from os import system, path, getcwd, remove, makedirs
from netaddr import IPNetwork, iter_iprange, IPAddress
from netaddr.core import AddrFormatError

class bcolors:
    """Used to provide color to logging output."""
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def get_args():
    """Provides an argument parser to collect options from the user."""
    parser = argparse.ArgumentParser(description="Scans a set of IPs quickly and provides detailed output using nmap and masscan.")
    verbosity = parser.add_mutually_exclusive_group()
    mass_args = parser.add_argument_group("Masscan Arguments")
    nmap_args = parser.add_argument_group("Nmap Arguments")
    req_args = parser.add_argument_group("Required Arguments")
    xtra_args = parser.add_argument_group("Extra Arguments")

    verbosity.add_argument("-v", "--verbose", action="store_true", help="Increases verbosity of the program.", default=False, required=False)
    verbosity.add_argument("-q", "--quiet", action="store_true", help="Decreases the verbosity of the program.", default=False, required=False)
    
    mass_args.add_argument("-mR", "--mass_rate", type=int, help="Tells masscan the packet rate you wish for it to use. Default is 20000.", default=20000, required=False)
    mass_args.add_argument("-mP", "--mass_ports", type=str, help="Tells masscan what ports you wish for it to scan. Default is 1-65535.", default="1-65535", required=False)

    #TODO: Maybe this shouldn't be default, I dunno.
    nmap_args.add_argument("-nE", "--no_extra_scans", action="store_true", help="Tells the program that you don't want to conduct extra scans using NSE scripts. This is on by default.", default=False, required=False)
    nmap_args.add_argument("-nT", "--nmap_threads", type=int, help="Tells the program how many concurrent nmap threads you wish to run at one time. Default is 20.", default=20, required=False)

    xtra_args.add_argument("-sS", "--screenshot", action="store_true", help="Tells the program that you want to take screenshots using selenium web driver of detected web pages.", default=False, required=False)
    xtra_args.add_argument("-pP", "--page_pulls", action="store_true", help="Tells the program that you want to pull down raw html code from discovered web pages.", default=False, required=False)
    xtra_args.add_argument("-gB", "--gobuster", type=str, help="Tells the program that you want to run gobuster on discovered https ports, you must provide a wordlist.", default=False, required=False)
    xtra_args.add_argument("-rN", "--nikto", action="store_true", help="Tells the program that you want to run nikto against discovered web pages.", default=False, required=False)

    #User can supply either a file or a list of IPs seperated by commas in various formats i.e. 192.168.10.0/24,192.168.10.1-192.168.10.40,192.168.10.24.
    req_args.add_argument("IPs", type=str, help="Provide the full location of an IP file or a comma seperated list of IPs. Can be formatted in any of the following ways: \
        192.168.1.1, 192.168.1.2-192.168.1.5, 192.168.1.0/24.")

    return verify_args(parser.parse_args())

def verify_args(arg_list):
    """Responsible for verifying various arguments to make sure they won't cause errors further down the line."""
    if arg_list.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    elif arg_list.quiet:
        logging.getLogger().setLevel(logging.WARNING)
    logging.debug("Verifying Arguments")
    if arg_list.screenshot:
        make_dirs("./results/nmap_http/screenshots")
    if arg_list.page_pulls:
        make_dirs("./results/nmap_http/html")
    if arg_list.gobuster:
        if not path.isfile(arg_list.gobuster):
            logging.critical("Failed to verify GoBuster wordlist: %s\nPlease try again." % arg_list.gobuster)
            exit()
        make_dirs("./results/nmap_http/gobuster")
    if arg_list.nikto:
        make_dirs("./results/nmap_http/nikto")
    return arg_list, verify_ips(arg_list.IPs), verify_ports(arg_list.mass_ports)

def verify_ips(to_verify):
    """
    Responsible for verifying that IP addresses are formatted properly.  IPs must first be valid in the xxx.xxx.xxx.xxx format.
    Next, IP ranges or CIDR addresses also need to be valid i.e. xxx.xxx.xxx.xxx-xxx.xxx.xxx.xxx or xxx.xxx.xxx.xxx/xx.  Also
    will take IP ranges or CIDR addresses and parse out each individual IP in the range and save it to a file for use by masscan.
    """
    logging.debug("Verifying IPs")
    try:
        addresses = []
        #Will try to open the string as a file, if it errors out it will be caught and the string will be interpreted as a list of IPs instead.
        try:
            with open(to_verify) as file:
                lines = file.read().splitlines()
        except FileNotFoundError:
            lines = to_verify.split(",")

        for i in lines:
            if "/" in i:
                for j in IPNetwork(i):
                    addresses.append(str(j))
            elif "-" in i:
                ip_range = i.split('-')
                for i in list(iter_iprange(ip_range[0], ip_range[1])):
                    addresses.append(str(i))
            else:
                addresses.append(str(IPAddress(i)))
        logging.debug("Finished Verifying IPs")

        write_ips(addresses)
        return addresses

    except AddrFormatError as err:
        logging.critical("Error with verifying IPs. Exiting Program.\nError: %s" % err)
        exit()

def verify_ports(to_verify):
    """
    Will attempt to verify the ports selected by the user.  I split this function into two for reusability and simplicity.  
    See check_ports.  This function is more meant to parse through the user input to make it easier to verify the values.
    """
    logging.debug("Verifying Ports")
    ports = ""
    for i in to_verify.split(","):
        if "-" in i:
            #For splitting ranges if the user supplies a range such as 20-56.
            for j in i.split("-"):
                check_ports(j)
            ports += "%s," % i
        elif check_ports(i):
            ports += "%s," % i
    logging.debug("Finished Verifying Ports")
    return ports[:-1]

def check_ports(to_check):
    """First will verify that the value is an integer, then will verify that the integer is within the 1-65535 range."""
    try:
        if not 1 <= int(to_check) <= 65535:
            logging.critical("Error with verifying ports. Exiting Program.\nError: Port values must be between 1 and 65535.")
            exit()
        else:
            return True

    except ValueError as err:
        logging.critical("Error with verifying ports. Exiting Program.\nError: %s" % err)
        exit()

def verify_versions():
    """Makes sure that the user has the correct versions of nmap and masscan installed."""
    #TODO:  Masscan apparently won't provide the right version if you do it this way. yum info shows proper version, need to fix.
    try:
        to_verify = {"nmap": "7.80", "masscan": "1.0.5"}
        for i in to_verify:
            logging.debug("Verifying that %s is version %s" % (i, to_verify[i]))
            output = subprocess.run(["/usr/bin/%s" % i, "--version"], capture_output=True)

            if "%s version %s" % (i, to_verify[i]) not in str(output).lower():
                logging.critical("Incorrect %s version, please update %s to %s. Exiting." % (i, i, to_verify[i]))
                exit()
            logging.debug("%s is version %s" % (i, to_verify[i]))
    
    except Exception as error:
        logging.critical("Error with verifying program versions: %s. Exiting." % error)
        exit()

def make_dirs(dir_to_make):
    """Will make directories required for the program to run correctly.  Definitely a better way to do this."""
    #TODO:  Make this better, maybe include this in the json file or something to make it easier to modify in the future.
    if not path.exists(dir_to_make):
        logging.debug("Making %s Directory" % dir_to_make)
        makedirs(dir_to_make)
    else:
        logging.debug("Directory %s Already Exists - Skipping" % dir_to_make)

def write_ips(addresses):
    """Writes provided ips to a file for use by masscan."""
    #TODO:  Have the program find the directory on its own.  This would be important if the user were to execute the program from some other directory.
    if path.isfile("./results/masscan/mass_ips.txt"):
        remove("./results/masscan/mass_ips.txt")
    with open("./results/masscan/mass_ips.txt", "w") as file:
        for i in addresses:
            file.write("%s\n" % i)

def get_formats(args):
    """Will get the formats for all scanners used in this program from a json file located in ./deps/formats.json."""
    #TODO:  Add formats for nmap etc.  Maybe add structure to include directories that need to be made, see make_dirs above.
    logging.debug("Importing Formats",)
    #Sets up a formats dictionary.
    formats = {}
    #Opens the formats.json file and reads the data.
    with open("./deps/formats.json", "r") as file:
        #Saves the data using pythons json module.
        data = json.load(file)
        #Loops through each scanner in the data variable.
        for i in data["scanners"]:
            #Saves all of the relevant data.
            scanner = i["scanner"]
            logging.debug("Importing %s Format" % scanner)
            formats[scanner] = add_scanner(i)
            logging.debug("Finished Importing %s Format" % scanner)
    logging.debug("Formatting Masscan With Arguments")
    formats['masscan'] = format_mass(formats['masscan'], args)
    logging.debug("Finished Formatting Masscan With Arguments")
    logging.debug("Finished Importing Formats")
    return formats

def add_scanner(scanner_to_add):
    """Interprets a scanner dictionary and converts it to a string that we can feed directly into a subprocess."""
    formatted_scanner = ""
    #We don't need the name of the scanner for this part so we get rid of it.
    scanner_to_add.pop('scanner')
    for i in scanner_to_add.keys():
        formatted_scanner += "%s " % scanner_to_add[i]
    return formatted_scanner[:-1]

def format_mass(to_format, args):
    """Will format the format with the user provided and/or default options."""
    #TODO:  Figure out a way to make this more reusable, might require some significant code modifications.
    return to_format % (args.mass_ports, "./results/masscan/mass_ips.txt", args.mass_rate, "./results/masscan/mass_results_" + time.strftime("%Y:%m:%d-%H:%M"))

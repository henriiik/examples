from ipaddress import ip_address, ip_network
from pulumi import Config, get_stack, get_project, StackReference

class Error(Exception):
    """Base class for exceptions in this module."""
    pass

class ConfigError(Error):
    """Exception raised for errors in Pulumi Config.

    Attributes:
        keys -- Config keys with the error
        message -- explanation of the error
    """
    def __init__(self, keys: [str], message: str):
        self.keys = keys
        self.message = message

# retrieve the stack configuration data
config = Config()

# retrieve the location
location = config.require('location')

# retrieve optional separator choice and suffix
separator = config.get('separator')
if not separator:
    separator = '-'
else:
    separator = separator[0]
if separator == ' ':
    separator = ''
suffix = config.get('suffix')
if not suffix:
    suffix = ''

# set default tags to be applied to all taggable resources
stack = get_stack()
default_tags = {
    'environment': stack
}

# Azure Bastion hosts in hub and spokes (until functional across peerings)
azure_bastion = config.get_bool('azure_bastion')

# Azure Firewall to route all Internet-bound traffic to designated next hop
forced_tunnel = config.get('forced_tunnel')
if forced_tunnel:
    ft_ip = ip_address(forced_tunnel) # check IP address is valid

# another stack may be peered in the same project, even across organizations
org = config.get('org')
peer = config.get('peer')
project = config.get('project')
if org and not project:
    project = get_project()
if not org:
    org = ''
if not project:
    project = ''
if not peer:
    reference = None
else:
    reference = StackReference(f'{org}/{project}/{peer}')

# validate firewall_address_space and hub_address_space
firewall_address_space = config.require('firewall_address_space')
fwz_nw = ip_network(firewall_address_space)
if not fwz_nw.is_private:
    raise ConfigError(['firewall_address_space'], 'must be private')
if fwz_nw.prefixlen > 24:
    raise ConfigError(['firewall_address_space'], 'must be /24 or larger')
hub_address_space = config.require('hub_address_space')
hub_nw = ip_network(hub_address_space)
if not hub_nw.is_private:
    raise ConfigError(['hub_address_space'], 'must be private')
if hub_nw.prefixlen > 24:
    raise ConfigError(['hub_address_space'], 'must be /24 or larger')
if fwz_nw.overlaps(hub_nw):
    raise ConfigError(
        ['firewall_address_space', 'hub_address_space'],
        'may not overlap'
    )

# locate hub_address_space within supernet for contiguous spoke_address_space
sup_diff = hub_nw.prefixlen - 8 # largest private IPv4 network is 10/8
super_nw = hub_nw.supernet(prefixlen_diff=sup_diff)
while not super_nw.is_private: # accommodate longer private network prefixes
    sup_diff = sup_diff - 1
    super_nw = hub_nw.supernet(prefixlen_diff=sup_diff)
if sup_diff <= 0:
    raise ConfigError(
        ['hub_address_space'],
        'must be a subnet of a private supernet'
    )
stack_sn = super_nw.subnets(prefixlen_diff=sup_diff)
hub_as = next(stack_sn)
while hub_as < hub_nw:
    hub_as = next(stack_sn)
if hub_address_space != str(hub_as):
    raise ConfigError(['hub_address_space'], 'check assumptions')

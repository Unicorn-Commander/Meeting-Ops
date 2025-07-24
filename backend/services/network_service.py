#!/usr/bin/env python3
"""
Network Management Service for Ubuntu Server
Handles network interfaces, IP configuration, DNS, and basic firewall management
"""

import os
import json
import subprocess
import yaml
import logging
from typing import Dict, List, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

class NetworkService:
    """Service for managing Ubuntu server network configuration"""
    
    def __init__(self):
        self.netplan_dir = Path("/etc/netplan")
        self.netplan_config = self.netplan_dir / "00-installer-config.yaml"
        
    async def get_network_interfaces(self) -> List[Dict[str, Any]]:
        """Get all network interfaces and their status"""
        try:
            # Get interface list
            result = subprocess.run(['ip', 'addr', 'show'], 
                                  capture_output=True, text=True, check=True)
            
            interfaces = []
            current_interface = None
            
            for line in result.stdout.split('\n'):
                line = line.strip()
                if not line:
                    continue
                    
                # Parse interface header
                if line.startswith(('1:', '2:', '3:', '4:', '5:', '6:', '7:', '8:', '9:')):
                    if current_interface:
                        interfaces.append(current_interface)
                    
                    parts = line.split(': ')
                    if len(parts) >= 2:
                        interface_name = parts[1].split('@')[0]
                        current_interface = {
                            'name': interface_name,
                            'state': 'UP' if 'UP' in line else 'DOWN',
                            'type': self._get_interface_type(interface_name),
                            'addresses': [],
                            'mac_address': None
                        }
                
                # Parse MAC address
                elif line.startswith('link/ether') and current_interface:
                    mac = line.split()[1]
                    current_interface['mac_address'] = mac
                
                # Parse IP addresses
                elif line.startswith('inet ') and current_interface:
                    ip_info = line.split()
                    ip_address = ip_info[1]
                    current_interface['addresses'].append({
                        'ip': ip_address.split('/')[0],
                        'prefix': ip_address.split('/')[1] if '/' in ip_address else '24',
                        'type': 'ipv4'
                    })
                elif line.startswith('inet6 ') and current_interface:
                    ip_info = line.split()
                    ip_address = ip_info[1]
                    current_interface['addresses'].append({
                        'ip': ip_address.split('/')[0],
                        'prefix': ip_address.split('/')[1] if '/' in ip_address else '64',
                        'type': 'ipv6'
                    })
            
            if current_interface:
                interfaces.append(current_interface)
                
            # Add interface statistics
            for interface in interfaces:
                interface['stats'] = await self._get_interface_stats(interface['name'])
                
            return interfaces
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get network interfaces: {e}")
            return []
    
    def _get_interface_type(self, interface_name: str) -> str:
        """Determine interface type based on name"""
        if interface_name.startswith('eth'):
            return 'ethernet'
        elif interface_name.startswith('wlan') or interface_name.startswith('wlp'):
            return 'wireless'
        elif interface_name.startswith('lo'):
            return 'loopback'
        elif interface_name.startswith('docker') or interface_name.startswith('br-'):
            return 'bridge'
        elif interface_name.startswith('veth'):
            return 'virtual'
        else:
            return 'unknown'
    
    async def _get_interface_stats(self, interface_name: str) -> Dict[str, int]:
        """Get network interface statistics"""
        try:
            stats_path = Path(f"/sys/class/net/{interface_name}/statistics")
            if not stats_path.exists():
                return {}
                
            stats = {}
            for stat_file in ['rx_bytes', 'tx_bytes', 'rx_packets', 'tx_packets', 'rx_errors', 'tx_errors']:
                stat_path = stats_path / stat_file
                if stat_path.exists():
                    stats[stat_file] = int(stat_path.read_text().strip())
                    
            return stats
        except Exception as e:
            logger.error(f"Failed to get stats for {interface_name}: {e}")
            return {}
    
    async def get_current_network_config(self) -> Dict[str, Any]:
        """Get current netplan configuration"""
        try:
            # Find netplan config files
            config_files = list(self.netplan_dir.glob("*.yaml")) + list(self.netplan_dir.glob("*.yml"))
            
            combined_config = {
                'network': {
                    'version': 2,
                    'ethernets': {},
                    'wifis': {}
                }
            }
            
            for config_file in config_files:
                if config_file.exists():
                    with open(config_file, 'r') as f:
                        config = yaml.safe_load(f)
                        if config and 'network' in config:
                            # Merge configurations
                            if 'ethernets' in config['network']:
                                combined_config['network']['ethernets'].update(config['network']['ethernets'])
                            if 'wifis' in config['network']:
                                combined_config['network']['wifis'].update(config['network']['wifis'])
            
            return combined_config
        except Exception as e:
            logger.error(f"Failed to read netplan config: {e}")
            return {'network': {'version': 2, 'ethernets': {}, 'wifis': {}}}
    
    async def update_interface_config(self, interface_name: str, config: Dict[str, Any]) -> bool:
        """Update network interface configuration"""
        try:
            # Get current config
            current_config = await self.get_current_network_config()
            
            # Determine interface type
            interface_type = self._get_interface_type(interface_name)
            
            if interface_type == 'ethernet':
                target_section = 'ethernets'
            elif interface_type == 'wireless':
                target_section = 'wifis'
            else:
                logger.error(f"Cannot configure interface type: {interface_type}")
                return False
            
            # Update configuration
            if target_section not in current_config['network']:
                current_config['network'][target_section] = {}
            
            current_config['network'][target_section][interface_name] = config
            
            # Write to netplan config
            backup_path = self.netplan_config.with_suffix('.yaml.backup')
            if self.netplan_config.exists():
                subprocess.run(['sudo', 'cp', str(self.netplan_config), str(backup_path)], check=True)
            
            # Write new config
            with open('/tmp/netplan_config.yaml', 'w') as f:
                yaml.dump(current_config, f, default_flow_style=False)
            
            # Move to netplan directory with sudo
            subprocess.run(['sudo', 'mv', '/tmp/netplan_config.yaml', str(self.netplan_config)], check=True)
            subprocess.run(['sudo', 'chmod', '600', str(self.netplan_config)], check=True)
            
            # Apply configuration
            result = subprocess.run(['sudo', 'netplan', 'apply'], 
                                  capture_output=True, text=True)
            
            if result.returncode != 0:
                logger.error(f"Netplan apply failed: {result.stderr}")
                # Restore backup
                if backup_path.exists():
                    subprocess.run(['sudo', 'mv', str(backup_path), str(self.netplan_config)], check=True)
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to update interface config: {e}")
            return False
    
    async def get_dns_config(self) -> Dict[str, Any]:
        """Get current DNS configuration"""
        try:
            dns_config = {
                'nameservers': [],
                'search_domains': [],
                'options': []
            }
            
            # Read /etc/resolv.conf
            resolv_conf = Path('/etc/resolv.conf')
            if resolv_conf.exists():
                with open(resolv_conf, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('nameserver '):
                            dns_config['nameservers'].append(line.split()[1])
                        elif line.startswith('search '):
                            dns_config['search_domains'].extend(line.split()[1:])
                        elif line.startswith('options '):
                            dns_config['options'].extend(line.split()[1:])
            
            # Also check systemd-resolved status
            try:
                result = subprocess.run(['systemd-resolve', '--status'], 
                                      capture_output=True, text=True)
                dns_config['systemd_resolved_status'] = result.stdout
            except:
                pass
                
            return dns_config
        except Exception as e:
            logger.error(f"Failed to get DNS config: {e}")
            return {'nameservers': [], 'search_domains': [], 'options': []}
    
    async def get_routing_table(self) -> List[Dict[str, Any]]:
        """Get current routing table"""
        try:
            result = subprocess.run(['ip', 'route', 'show'], 
                                  capture_output=True, text=True, check=True)
            
            routes = []
            for line in result.stdout.split('\n'):
                line = line.strip()
                if not line:
                    continue
                    
                parts = line.split()
                if len(parts) >= 3:
                    route = {
                        'destination': parts[0],
                        'gateway': None,
                        'interface': None,
                        'metric': None,
                        'raw': line
                    }
                    
                    # Parse route details
                    for i, part in enumerate(parts):
                        if part == 'via' and i + 1 < len(parts):
                            route['gateway'] = parts[i + 1]
                        elif part == 'dev' and i + 1 < len(parts):
                            route['interface'] = parts[i + 1]
                        elif part == 'metric' and i + 1 < len(parts):
                            route['metric'] = parts[i + 1]
                    
                    routes.append(route)
            
            return routes
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get routing table: {e}")
            return []
    
    async def get_firewall_status(self) -> Dict[str, Any]:
        """Get UFW firewall status"""
        try:
            # Check UFW status
            result = subprocess.run(['sudo', 'ufw', 'status', 'verbose'], 
                                  capture_output=True, text=True)
            
            firewall_status = {
                'enabled': 'Status: active' in result.stdout,
                'default_policy': {},
                'rules': [],
                'raw_output': result.stdout
            }
            
            # Parse UFW output
            lines = result.stdout.split('\n')
            in_rules_section = False
            
            for line in lines:
                line = line.strip()
                
                if 'Default:' in line:
                    # Parse default policies
                    if 'deny (incoming)' in line:
                        firewall_status['default_policy']['incoming'] = 'deny'
                    elif 'allow (incoming)' in line:
                        firewall_status['default_policy']['incoming'] = 'allow'
                    
                    if 'allow (outgoing)' in line:
                        firewall_status['default_policy']['outgoing'] = 'allow'
                    elif 'deny (outgoing)' in line:
                        firewall_status['default_policy']['outgoing'] = 'deny'
                
                elif line.startswith('--'):
                    in_rules_section = True
                elif in_rules_section and line and not line.startswith('To'):
                    # Parse firewall rules
                    parts = line.split()
                    if len(parts) >= 3:
                        firewall_status['rules'].append({
                            'to': parts[0] if len(parts) > 0 else '',
                            'action': parts[1] if len(parts) > 1 else '',
                            'from': parts[2] if len(parts) > 2 else '',
                            'raw': line
                        })
            
            return firewall_status
        except Exception as e:
            logger.error(f"Failed to get firewall status: {e}")
            return {'enabled': False, 'default_policy': {}, 'rules': []}
    
    async def get_system_network_info(self) -> Dict[str, Any]:
        """Get comprehensive system network information"""
        try:
            info = {
                'hostname': '',
                'domain': '',
                'interfaces': await self.get_network_interfaces(),
                'dns': await self.get_dns_config(),
                'routes': await self.get_routing_table(),
                'firewall': await self.get_firewall_status(),
                'network_config': await self.get_current_network_config()
            }
            
            # Get hostname
            try:
                result = subprocess.run(['hostname'], capture_output=True, text=True, check=True)
                info['hostname'] = result.stdout.strip()
            except:
                pass
            
            # Get domain
            try:
                result = subprocess.run(['hostname', '-d'], capture_output=True, text=True)
                info['domain'] = result.stdout.strip()
            except:
                pass
            
            return info
        except Exception as e:
            logger.error(f"Failed to get system network info: {e}")
            return {}

# Global network service instance
network_service = NetworkService()
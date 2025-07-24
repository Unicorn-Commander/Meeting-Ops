#!/usr/bin/env python3
"""
Network Management API Endpoints
Provides network configuration and monitoring for Ubuntu server
"""

from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import logging

from services.network_service import network_service
from auth.dependencies import get_current_user, require_permission
from auth.models import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/network", tags=["network"])

class InterfaceConfig(BaseModel):
    """Network interface configuration"""
    dhcp4: Optional[bool] = None
    dhcp6: Optional[bool] = None
    addresses: Optional[List[str]] = None
    gateway4: Optional[str] = None
    gateway6: Optional[str] = None
    nameservers: Optional[Dict[str, List[str]]] = None
    routes: Optional[List[Dict[str, Any]]] = None

class FirewallRule(BaseModel):
    """Firewall rule configuration"""
    action: str = Field(..., description="allow, deny, or reject")
    direction: str = Field(..., description="in, out, or both")
    port: Optional[str] = None
    protocol: Optional[str] = None
    from_ip: Optional[str] = None
    to_ip: Optional[str] = None

class NetworkSettings(BaseModel):
    """Network system settings"""
    hostname: Optional[str] = None
    domain: Optional[str] = None
    dns_servers: Optional[List[str]] = None
    search_domains: Optional[List[str]] = None

@router.get("/interfaces")
async def get_network_interfaces(
    current_user: User = Depends(get_current_user)
):
    """Get all network interfaces and their current status"""
    try:
        interfaces = await network_service.get_network_interfaces()
        return {
            "interfaces": interfaces,
            "count": len(interfaces)
        }
    except Exception as e:
        logger.error(f"Failed to get network interfaces: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve network interfaces"
        )

@router.get("/status")
async def get_network_status(
    current_user: User = Depends(get_current_user)
):
    """Get comprehensive network system status"""
    try:
        network_info = await network_service.get_system_network_info()
        return network_info
    except Exception as e:
        logger.error(f"Failed to get network status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve network status"
        )

@router.get("/config")
async def get_network_config(
    current_user: User = Depends(require_permission("admin"))
):
    """Get current netplan network configuration (admin only)"""
    try:
        config = await network_service.get_current_network_config()
        return config
    except Exception as e:
        logger.error(f"Failed to get network config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve network configuration"
        )

@router.put("/interfaces/{interface_name}")
async def update_interface_config(
    interface_name: str,
    config: InterfaceConfig,
    current_user: User = Depends(require_permission("admin"))
):
    """Update network interface configuration (admin only)"""
    try:
        # Convert Pydantic model to dict and filter None values
        config_dict = {k: v for k, v in config.dict().items() if v is not None}
        
        success = await network_service.update_interface_config(interface_name, config_dict)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to update interface configuration"
            )
        
        return {
            "message": f"Interface {interface_name} configuration updated successfully",
            "interface": interface_name,
            "config": config_dict
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update interface {interface_name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update interface configuration"
        )

@router.get("/dns")
async def get_dns_config(
    current_user: User = Depends(get_current_user)
):
    """Get current DNS configuration"""
    try:
        dns_config = await network_service.get_dns_config()
        return dns_config
    except Exception as e:
        logger.error(f"Failed to get DNS config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve DNS configuration"
        )

@router.get("/routes")
async def get_routing_table(
    current_user: User = Depends(get_current_user)
):
    """Get current routing table"""
    try:
        routes = await network_service.get_routing_table()
        return {
            "routes": routes,
            "count": len(routes)
        }
    except Exception as e:
        logger.error(f"Failed to get routing table: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve routing table"
        )

@router.get("/firewall")
async def get_firewall_status(
    current_user: User = Depends(get_current_user)
):
    """Get UFW firewall status and rules"""
    try:
        firewall_status = await network_service.get_firewall_status()
        return firewall_status
    except Exception as e:
        logger.error(f"Failed to get firewall status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve firewall status"
        )

@router.post("/firewall/enable")
async def enable_firewall(
    current_user: User = Depends(require_permission("admin"))
):
    """Enable UFW firewall (admin only)"""
    try:
        import subprocess
        result = subprocess.run(['sudo', 'ufw', '--force', 'enable'], 
                              capture_output=True, text=True)
        
        if result.returncode != 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to enable firewall: {result.stderr}"
            )
        
        return {"message": "Firewall enabled successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to enable firewall: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to enable firewall"
        )

@router.post("/firewall/disable")
async def disable_firewall(
    current_user: User = Depends(require_permission("admin"))
):
    """Disable UFW firewall (admin only)"""
    try:
        import subprocess
        result = subprocess.run(['sudo', 'ufw', 'disable'], 
                              capture_output=True, text=True)
        
        if result.returncode != 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to disable firewall: {result.stderr}"
            )
        
        return {"message": "Firewall disabled successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to disable firewall: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to disable firewall"
        )

@router.post("/firewall/rules")
async def add_firewall_rule(
    rule: FirewallRule,
    current_user: User = Depends(require_permission("admin"))
):
    """Add UFW firewall rule (admin only)"""
    try:
        import subprocess
        
        # Build UFW command
        cmd = ['sudo', 'ufw']
        
        # Add direction
        if rule.direction == 'in':
            cmd.append('allow')
            cmd.append('in')
        elif rule.direction == 'out':
            cmd.append('allow')
            cmd.append('out')
        else:
            cmd.append(rule.action)
        
        # Add port and protocol
        if rule.port:
            if rule.protocol:
                cmd.append(f"{rule.port}/{rule.protocol}")
            else:
                cmd.append(rule.port)
        
        # Add from/to addresses
        if rule.from_ip:
            cmd.extend(['from', rule.from_ip])
        if rule.to_ip:
            cmd.extend(['to', rule.to_ip])
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to add firewall rule: {result.stderr}"
            )
        
        return {
            "message": "Firewall rule added successfully",
            "rule": rule.dict(),
            "command": ' '.join(cmd)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to add firewall rule: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add firewall rule"
        )

@router.get("/connectivity/test")
async def test_connectivity(
    target: str = "8.8.8.8",
    current_user: User = Depends(get_current_user)
):
    """Test network connectivity to a target host"""
    try:
        import subprocess
        
        # Ping test
        ping_result = subprocess.run(
            ['ping', '-c', '3', '-W', '5', target],
            capture_output=True, text=True
        )
        
        # DNS test
        dns_result = subprocess.run(
            ['nslookup', target],
            capture_output=True, text=True
        )
        
        return {
            "target": target,
            "ping": {
                "success": ping_result.returncode == 0,
                "output": ping_result.stdout,
                "error": ping_result.stderr
            },
            "dns": {
                "success": dns_result.returncode == 0,
                "output": dns_result.stdout,
                "error": dns_result.stderr
            }
        }
    except Exception as e:
        logger.error(f"Failed to test connectivity: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to test network connectivity"
        )

@router.post("/settings")
async def update_network_settings(
    settings: NetworkSettings,
    current_user: User = Depends(require_permission("admin"))
):
    """Update system network settings (admin only)"""
    try:
        import subprocess
        results = []
        
        # Update hostname
        if settings.hostname:
            result = subprocess.run(
                ['sudo', 'hostnamectl', 'set-hostname', settings.hostname],
                capture_output=True, text=True
            )
            results.append({
                "setting": "hostname",
                "success": result.returncode == 0,
                "error": result.stderr if result.returncode != 0 else None
            })
        
        # Update DNS settings would require modifying netplan config
        # This is more complex and should be done through interface config
        
        return {
            "message": "Network settings updated",
            "results": results
        }
    except Exception as e:
        logger.error(f"Failed to update network settings: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update network settings"
        )
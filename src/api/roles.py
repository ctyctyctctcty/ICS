from copy import deepcopy
from typing import Any, Dict

from .utils import url_quote

ROLE_TEMPLATE = {
    "enterprise-onboarding": {
        "auto-launch": "false",
        "install-junospulse": "false",
        "redirect-mdm-server-url": "",
        "use-tpmdm-onboard": "false",
    },
    "files": {
        "file-bookmarks": {
            "file-win-bookmarks": {"bookmark": []}
        },
        "file-win-options": {
            "user-add-bookmarks": "false",
            "user-browse-share": "false",
        },
    },
    "general": {
        "overview": {
            "access-features": {
                "email": "false",
                "html5-access": "false",
                "network-connect": "true",
                "sam": "false",
                "secure-mail": "false",
                "terminal-services": "false",
                "virtual-desktops": "false",
                "web": "false",
                "windows-files": "false",
            },
            "description": "Internet Access Only",
            "enterprise-onboarding": {"enterprise-onboarding-enabled": "false"},
            "options": {
                "junos-pulse": "true",
                "session-options": "true",
                "ui-options": "true",
                "vlan-source-ip": "false",
            },
        },
        "restrictions": {
            "browser": {
                "customized": "any-user-agent",
                "user-agent-patterns": {"user-agent-pattern": []},
            },
            "certificate": {
                "cert-key-value-pairs": {"cert-key-value-pair": []},
                "customized": "allow-all-users",
            },
            "host-checker": {
                "host-check-enforce": "disable",
                "host-check-match": "all",
                "host-check-policies": None,
            },
            "mobile": {
                "server-certificate-trust-enforcement": "disable",
                "touch-id-supported": "disable",
            },
            "source-ip": {
                "customized": "any-ip",
                "ips": {"ip": []},
            },
        },
        "session-options": {
            "http-only-device-cookie": "enabled",
            "idle-timeout": "10",
            "max-timeout": "60",
            "netmask": "255.255.255.255",
            "persist-passwords": "disabled",
            "persist-session-cookie": "disabled",
            "prefix": "64",
            "reminder-time": "5",
            "remove-browser-session-cookie": "disabled",
            "request-follow-through": "disabled",
            "roaming": "disabled",
            "session-extension": "false",
            "session-idle-timeout-skip": "disabled",
            "session-timeout-relogin": "true",
            "session-timeout-warning": "false",
            "session-upload-log": "false",
            "use-auth-srvr-attr-for-session-mgmt": "false",
        },
        "ui-options": {
            "accordion-view": "Block",
            "always-show-notification-nc": "false",
            "browsing-toolbar": "standard",
            "browsing-toolbar-logo-destination": "start-page-settings",
            "browsing-toolbar-logo-url": "",
            "browsing-toolbar-logo-url-allow-sub": "false",
            "browsing-toolbar-show-addbk": "true",
            "browsing-toolbar-show-fav": "true",
            "browsing-toolbar-show-help": "true",
            "browsing-toolbar-show-home": "false",
            "browsing-toolbar-show-session-timer": "false",
            "browsing-toolbar-withiframe": "false",
            "compliance-failure-message": "You have limited connectivity because your device does not meet compliance policies.",
            "custom-help-page-height": "300",
            "custom-help-page-width": "400",
            "custom-help-url": "",
            "custom-help-url-allow-sub": "false",
            "custom-page-url": "",
            "custom-page-url-allow-sub": "false",
            "display-client-applications": "false",
            "display-home": "true",
            "display-preferences": "true",
            "display-session-counter": "false",
            "header-background-color": "#FFFFFF",
            "help-url": "standard",
            "left-panel-order": [
                "Welcome",
                "Web Bookmarks",
                "Files",
                "Terminal Sessions",
                "Client Application Sessions",
                "Virtual Desktops",
            ],
            "notification-message": "",
            "onboarding-messages": {
                "android-and-iOS-secure-mail-disabled": {"download-configuration-profile": ""},
                "android-and-iOS-secure-mail-enabled": {"install-junos-pulse": ""},
                "welcome-message": "",
                "windows": {"download-application": "", "post-downloading": ""},
            },
            "portal-name": "Ivanti Connect Secure",
            "right-panel-order": None,
            "show-compliance-failure": "false",
            "show-copyright": "true",
            "show-notification": "false",
            "show-notification-nc": "false",
            "show-username": "true",
            "signin-notification-id": "None",
            "start-page": "bookmarks-page",
            "sub-header-background-color": "#336699",
            "sub-header-font-color": "#FFFFFF",
            "welcome-message": "Welcome to the",
        },
        "vlan-source-ip": {
            "source-ip": "Interface IP",
            "vlan": "Internal Port IP",
        },
    },
    "html5-access": {
        "html5-access-options": {
            "add-rdp-sessions": "false",
            "add-ssh-sessions": "false",
            "add-telnet-sessions": "false",
            "add-vnc-sessions": "false",
            "allow-add-sessions": "false",
            "disable-sso": "false",
            "enable-admin-side-recording": "false",
            "enable-launcher": "false",
            "rdp-options": {
                "connect-console": "false",
                "console-audio": "false",
                "disable-audio": "false",
                "enable-audio-recording": "false",
                "enable-camera": "false",
                "enable-copy": "false",
                "enable-desktop-composition": "false",
                "enable-font-smoothing": "false",
                "enable-full-window-drag": "false",
                "enable-menu-animations": "false",
                "enable-multi-monitor": "false",
                "enable-printing": "false",
                "enable-resolution": "false",
                "enable-session-recording": "false",
                "enable-sound-quality": "false",
                "enable-theming": "false",
                "enable-wallpaper": "false",
                "remote-drive": "false",
                "smartcard-login": "false",
            },
            "ssh-options": {"enable-SFTP": "false", "enable-copy": "false"},
            "telnet-options": {"enable-copy": "false"},
            "vnc-options": {"enable-copy": "false", "ignore-cursor": "false", "track-cursor": "false"},
        },
        "sessions": {"session": []},
    },
    "name": "Internet Access",
    "network-connect": {
        "auto-launch": "false",
        "auto-uninstall": "false",
        "client-check": "false",
        "client-ui-mode-desktop": "neux",
        "client-ui-mode-mobile": "neux",
        "disallow-client-proxy": "false",
        "disallow-client-upgrade": "false",
        "gina-option": "nc-start-windows-logging",
        "install-gina": "false",
        "linux-endscript": "",
        "linux-startscript": "",
        "mac-endscript": "",
        "mac-startscript": "",
        "multicast": "false",
        "pulse-settings": {"client-components": "Default", "integration": "false"},
        "split-tunneling-enable": "false",
        "split-tunneling-ip6-traffic-enforcement": "false",
        "split-tunneling-route-monitor": "false",
        "split-tunneling-route-override": "false",
        "split-tunneling-traffic-enforcement": "false",
        "tos-bits-copy": "false",
        "win-skip-startscript": "false",
        "windows-endscript": "",
        "windows-startscript": "",
    },
    "sam": {
        "jsam-applications": {"jsam-application": []},
        "sam-options": {
            "auto-allow": "false",
            "auto-launch": "false",
            "jsam-addapps": "false",
            "jsam-autoclose": "true",
            "jsam-hostmapping": "false",
            "jsam-registrycheck": "false",
            "wsam-autouninstall": "false",
            "wsam-autoupgrade": "true",
            "wsam-dns-filtering": "false",
            "wsam-endscript": "",
            "wsam-endscript-mac": "",
            "wsam-prompt": "false",
            "wsam-startscript": "",
            "wsam-startscript-mac": "",
            "wsam-tdi-failover": "false",
        },
        "wsam-allowed-servers": {"default-action": "allow", "wsam-allowed-server": []},
        "wsam-applications": {"wsam-application": []},
        "wsam-bypass-apps": {"wsam-bypass-app": []},
    },
    "terminal-services": {
        "sessions": {"session": []},
        "terminal-services-options": {
            "allow-add-sessions": "false",
            "allow-clipboard": "false",
            "auto-allow-termserv-session": "false",
            "client-delivery": "download-citrixweb",
            "connect-comports": "false",
            "connect-drives": "false",
            "connect-printers": "false",
            "connect-smartcards": "false",
            "connect-sounddevices": "false",
            "disable-nla": "false",
            "disable-sso": "false",
            "download-url": "",
            "download-version": "",
            "enable-rdp-launcher": "false",
            "experience-optinos": {
                "bitmap-caching": "false",
                "desktop-background": "false",
                "desktop-composition": "false",
                "font-smoothing": "false",
                "menu-window-animation": "false",
                "show-content-dragging": "false",
                "themes": "false",
            },
            "microphone-option": "false",
            "multi-mon": "false",
            "smartcard-nla": "disabled",
        },
    },
    "virtual-desktops": {"sessions": {"session": []}},
    "web": {
        "web-bookmarks": {"bookmark": []},
        "web-options": {
            "browsing-untrusted-sslsites": "true",
            "domain-info": "true",
            "flash-content": "false",
            "hpxproxy-connection-timeout": "1800",
            "http-connection-timeout": "240",
            "java-applets": "true",
            "mask-hostname": "false",
            "persistent-cookies": "false",
            "rewrite-file-urls": "false",
            "rewrite-links-pdf": "false",
            "unrewritten-page-newwindow": "false",
            "user-add-bookmarks": "false",
            "user-enter-url": "false",
            "users-bypass-warnings": "false",
            "warn-certificate-issues": "true",
            "websocket-connection-timeout": "900",
        },
    },
}


def role_endpoint(settings: Dict[str, Any], role_name: str) -> str:
    return settings['ics']['endpoints']['role_item'].format(name=url_quote(role_name))


def get_role(client, settings: Dict[str, Any], role_name: str):
    path = role_endpoint(settings, role_name)
    response = client.session.get(client._full_url(path), timeout=client.timeout)
    if response.status_code == 404:
        return None
    if response.status_code in (401, 403):
        client.authenticate()
        response = client.session.get(client._full_url(path), timeout=client.timeout)
    response.raise_for_status()
    return response.json() if response.text.strip() else {}


def build_role_payload(role_name: str, description: str) -> Dict[str, Any]:
    payload = deepcopy(ROLE_TEMPLATE)
    payload['name'] = role_name
    payload['general']['overview']['description'] = description
    return payload


def build_role_update_payload(existing: Dict[str, Any], role_name: str, description: str) -> Dict[str, Any]:
    payload = deepcopy(existing)
    payload['name'] = role_name
    payload.setdefault('general', {}).setdefault('overview', {})['description'] = description
    return payload

def _needs_update(existing: Dict[str, Any], desired: Dict[str, Any]) -> bool:
    return existing != desired


def ensure_role(client, settings: Dict[str, Any], logger, role_name: str, description: str) -> str:
    existing = get_role(client, settings, role_name)

    if existing is None:
        desired = build_role_payload(role_name, description)
        create_path = settings['ics']['endpoints']['role_create']
        client.post_json(create_path, desired)
        logger.info('Role created: %s', role_name)
        return 'created'

    desired = build_role_update_payload(existing, role_name, description)
    if _needs_update(existing, desired):
        path = role_endpoint(settings, role_name)
        client.put_json(path, desired)
        logger.info('Role updated: %s', role_name)
        return 'updated'

    logger.info('Role already exists. skip: %s', role_name)
    return 'skip'

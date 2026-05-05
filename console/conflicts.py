import socket


def get_local_ips() -> list[str]:
    """获取本机所有非回环 IP 地址，IPv4 优先"""
    ips: list[str] = []
    hostname = socket.gethostname()
    try:
        for addrs in socket.getaddrinfo(hostname, None):
            ip = str(addrs[4][0])
            if ip.startswith('127.') or ip == '::1':
                continue
            if ip not in ips:
                ips.append(ip)
    except socket.gaierror:
        pass
    if not ips:
        try:
            import psutil

            for _, addrs in psutil.net_if_addrs().items():
                for addr in addrs:
                    if addr.family == socket.AF_INET and not addr.address.startswith('127.'):
                        ips.append(addr.address)
        except ImportError:
            pass
    # IPv4 优先排列
    v4: list[str] = [ip for ip in ips if '.' in ip]
    v6: list[str] = [ip for ip in ips if ':' in ip]
    return v4 + v6

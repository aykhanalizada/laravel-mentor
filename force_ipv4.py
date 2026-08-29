"""Şəbəkə çağırışlarını IPv4-ə məcbur edir.

Bu maşında api.telegram.org üçün AAAA (IPv6) yazısı qayıdır, amma IPv6 default
route yoxdur. Python bəzən həmin ölü ünvanı seçir və [Errno 101] Network is
unreachable atır — bot mesajları itirir.

Import etmək kifayətdir; getaddrinfo nəticəsindən IPv6 ünvanları süzülür.
IPv4 ümumiyyətlə yoxdursa, orijinal siyahı qaytarılır (yəni saf IPv6 şəbəkədə
də sınmır).
"""
import socket

_orig_getaddrinfo = socket.getaddrinfo


def _ipv4_only(host, port, family=0, type=0, proto=0, flags=0):
    results = _orig_getaddrinfo(host, port, family, type, proto, flags)
    ipv4 = [r for r in results if r[0] == socket.AF_INET]
    return ipv4 or results


socket.getaddrinfo = _ipv4_only

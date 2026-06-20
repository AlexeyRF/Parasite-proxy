import asyncio
import ssl
import struct
import socket
import logging



BRIDGE_HOST = '0.0.0.0'
PORT_CONTROL = 8443 
PORT_SOCKS = 1080    
POOL_SIZE = 5
SOCKS_USER = 'user'
SOCKS_PASS = 'pass'

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(asctime)s %(message)s')

worker_pool = asyncio.Queue()

async def handle_worker(reader, writer):
    peer = writer.get_extra_info('peername')
    logging.info(f"Worker connected: {peer}")
    await worker_pool.put((reader, writer))

async def socks5_handshake(reader, writer):
    try:
        header = await reader.readexactly(2)
        version, nmethods = struct.unpack('!BB', header)
        if version != 5:
            return None
        methods = await reader.readexactly(nmethods)
        
        if b'\x02' not in methods:
            writer.write(struct.pack('!BB', 5, 0xFF)) 
            await writer.drain()
            return None
        
        writer.write(struct.pack('!BB', 5, 0x02))
        await writer.drain()

        auth_header = await reader.readexactly(2)
        auth_ver, ulen = struct.unpack('!BB', auth_header)
        username = (await reader.readexactly(ulen)).decode()
        plen = (await reader.readexactly(1))[0]
        password = (await reader.readexactly(plen)).decode()

        if username == SOCKS_USER and password == SOCKS_PASS:
            writer.write(struct.pack('!BB', 1, 0x00))
            await writer.drain()
        else:
            writer.write(struct.pack('!BB', 1, 0x01))  
            await writer.drain()
            return None

        req_header = await reader.readexactly(4)
        ver, cmd, rsv, atyp = struct.unpack('!BBBB', req_header)
        
        if cmd != 0x01:  
            return None

        if atyp == 0x01: 
            addr = socket.inet_ntoa(await reader.readexactly(4))
        elif atyp == 0x03:  
            alen = (await reader.readexactly(1))[0]
            addr = (await reader.readexactly(alen)).decode()
        elif atyp == 0x04:  
            addr = socket.inet_ntop(socket.AF_INET6, await reader.readexactly(16))
        else:
            return None

        port = struct.unpack('!H', await reader.readexactly(2))[0]
        return addr, port
    except Exception as e:
        logging.error(f"SOCKS5 handshake error: {e}")
        return None

async def pipe(reader, writer):
    try:
        while True:
            data = await reader.read(8192)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except:
        pass
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except:
            pass

async def handle_client(reader, writer):

    target = await socks5_handshake(reader, writer)
    if not target:
        writer.close()
        return

    host, port = target
    logging.info(f"SOCKS5 request: {host}:{port}")

    try:
        worker_reader, worker_writer = await asyncio.wait_for(worker_pool.get(), timeout=10)
    except asyncio.TimeoutError:
        logging.warning("No workers available")
        writer.write(struct.pack('!BBBBIH', 5, 0x04, 0x00, 0x01, 0, 0))
        await writer.drain()
        writer.close()
        return

    try:
        host_bytes = host.encode()
        worker_writer.write(struct.pack('!B', len(host_bytes)) + host_bytes + struct.pack('!H', port))
        await worker_writer.drain()
        status = await worker_reader.readexactly(1)
        if status != b'\x00':
            logging.error(f"Worker failed to connect to {host}:{port}")
            writer.write(struct.pack('!BBBBIH', 5, 0x04, 0x00, 0x01, 0, 0))
            await writer.drain()
            writer.close()
            worker_writer.close()
            return

        writer.write(struct.pack('!BBBBIH', 5, 0x00, 0x00, 0x01, 0, 0))
        await writer.drain()

        await asyncio.gather(
            pipe(reader, worker_writer),
            pipe(worker_reader, writer)
        )
    except Exception as e:
        logging.error(f"Bridging error: {e}")
        writer.close()
        worker_writer.close()

async def main():
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    try:
        ssl_context.load_cert_chain('cert.pem', 'key.pem')
    except FileNotFoundError:
        logging.error("cert.pem or key.pem not found. Please generate them first.")
        logging.error("Run: openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes")
        return

    control_server = await asyncio.start_server(handle_worker, BRIDGE_HOST, PORT_CONTROL, ssl=ssl_context)
    socks_server = await asyncio.start_server(handle_client, BRIDGE_HOST, PORT_SOCKS)

    logging.info(f"Control server listening on {BRIDGE_HOST}:{PORT_CONTROL} (TLS)")
    logging.info(f"SOCKS5 server listening on {BRIDGE_HOST}:{PORT_SOCKS} (Auth: {SOCKS_USER}:{SOCKS_PASS})")

    async with control_server, socks_server:
        await asyncio.gather(control_server.serve_forever(), socks_server.serve_forever())

if __name__ == '__main__':
    asyncio.run(main())

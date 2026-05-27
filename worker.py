import asyncio
import ssl
import struct

BRIDGE_HOST = '127.0.0.1'  # Замени на адрес сервера - моста
PORT_CONTROL = 8443
POOL_SIZE = 5

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

async def worker_connection(ssl_context):
    try:
        reader, writer = await asyncio.open_connection(BRIDGE_HOST, PORT_CONTROL, ssl=ssl_context)
        print("[*] Worker connection established and waiting...")

        header = await reader.readexactly(1)
        host_len = header[0]
        host = (await reader.readexactly(host_len)).decode()
        port = struct.unpack('!H', await reader.readexactly(2))[0]

        print(f"[*] Connecting to target: {host}:{port}")

        try:
            target_reader, target_writer = await asyncio.open_connection(host, port)
            writer.write(b'\x00')
            await writer.drain()
            
            await asyncio.gather(
                pipe(reader, target_writer),
                pipe(target_reader, writer)
            )
        except Exception as e:
            print(f"[!] Failed to connect to {host}:{port}: {e}")
            writer.write(b'\x01')
            await writer.drain()
            writer.close()
            await writer.wait_closed()

    except Exception as e:
        print(f"[!] Worker connection error: {e}")

async def pool_manager():
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    while True:
        tasks = [worker_connection(ssl_context) for _ in range(POOL_SIZE)]
        await asyncio.gather(*tasks)
        print("[*] Restarting worker pool...")
        await asyncio.sleep(1)

if __name__ == '__main__':
    print(f"[*] Starting worker pool (target: {BRIDGE_HOST}:{PORT_CONTROL})")
    try:
        asyncio.run(pool_manager())
    except KeyboardInterrupt:
        pass

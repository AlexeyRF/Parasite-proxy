import asyncio
import ssl
import struct
import logging


BRIDGE_HOST = '127.0.0.1'  # Replace with bridge server address
PORT_CONTROL = 8443
POOL_SIZE = 5

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(asctime)s %(message)s')


async def pipe(reader, writer):
    try:
        while True:
            data = await reader.read(8192)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except Exception:
        pass
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass

async def worker_connection(ssl_context):
    while True:
        try:
            reader, writer = await asyncio.open_connection(BRIDGE_HOST, PORT_CONTROL, ssl=ssl_context)
            logging.info("Worker connection established and waiting...")

            header = await reader.readexactly(1)
            host_len = header[0]
            host = (await reader.readexactly(host_len)).decode()
            port = struct.unpack('!H', await reader.readexactly(2))[0]

            logging.info(f"Connecting to target: {host}:{port}")

            try:
                target_reader, target_writer = await asyncio.open_connection(host, port)
                writer.write(b'\x00')
                await writer.drain()

                await asyncio.gather(
                    pipe(reader, target_writer),
                    pipe(target_reader, writer)
                )
            except Exception as e:
                logging.error(f"Failed to connect/pipe to {host}:{port}: {e}")
                writer.write(b'\x01')
                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()

        except Exception as e:
            logging.error(f"Worker connection error: {e}")
            await asyncio.sleep(5)  # wait before retrying on error

async def pool_manager():
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    logging.info(f"Starting worker pool of size {POOL_SIZE} (target: {BRIDGE_HOST}:{PORT_CONTROL})")
    tasks = [asyncio.create_task(worker_connection(ssl_context)) for _ in range(POOL_SIZE)]
    await asyncio.gather(*tasks)

if __name__ == '__main__':
    try:
        asyncio.run(pool_manager())
    except KeyboardInterrupt:
        logging.info("Worker pool interrupted by user.")

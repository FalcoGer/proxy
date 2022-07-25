# struct is used to decode bytes into primitive data types
import struct
# queue is used as a thread safe data structure for packets to be sent to the client or server
import queue

SERVER_QUEUE = queue.SimpleQueue()
CLIENT_QUEUE = queue.SimpleQueue()

def parse(data, port, origin):
    sign = '->' if origin == 'client' else '<-'
    print(f"c{sign}s: {data}")
    # do interesting stuff with the data!
    # don't append to queue to just drop the package
    if data.find(b'fuck') >= 0:
        print("Dropped")
        return
    if (origin == 'client'):
        SERVER_QUEUE.put(data)
    elif (origin == 'server'):
        CLIENT_QUEUE.put(data)


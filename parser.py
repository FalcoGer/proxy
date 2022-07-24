SERVER_QUEUE = []
CLIENT_QUEUE = []

def parse(data, port, origin):
    sign = '->' if origin == 'client' else '<-'
    print(f"c{sign}s: {data}")
    # do interesting stuff with the data!
    # don't append to queue to just drop the package
    if data.find(b'fuck') >= 0:
        print("Dropped")
        return
    if (origin == 'client'):
        SERVER_QUEUE.append(data)
    elif (origin == 'server'):
        CLIENT_QUEUE.append(data)


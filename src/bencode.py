

class Bencode:
    """
    helpers for bencoding
    """
    @staticmethod
    def bencode_decode(data: bytes) -> dict:
        def decode(index: int):
            if data[index:index + 1] == b'i':
                end = data.index(b'e', index)
                number = int(data[index + 1:end])
                return number, end + 1

            elif data[index:index + 1].isdigit():
                colon = data.index(b':', index)
                length = int(data[index:colon])
                start = colon + 1
                end = start + length
                raw = data[start:end]
                try:
                    return raw.decode('utf-8'), end
                except UnicodeDecodeError:
                    return raw, end

            elif data[index:index + 1] == b'l':
                index += 1
                lst = []
                while data[index:index + 1] != b'e':
                    item, index = decode(index)
                    lst.append(item)
                return lst, index + 1

            elif data[index:index + 1] == b'd':
                index += 1
                dct = {}
                while data[index:index + 1] != b'e':
                    key, index = decode(index)
                    value, index = decode(index)
                    dct[key] = value
                return dct, index + 1

            else:
                raise ValueError(f"Invalid bencode at index {index}: {data[index:index + 10]}")

        value, final_index = decode(0)
        if final_index != len(data):
            raise ValueError("Extra data after decoding")
        return value

from io import BytesIO
import unittest

from mini_redis.protocol.resp import RespCodec


class RespCodecTest(unittest.TestCase):
    def test_command_uses_resp_array_of_bulk_strings(self) -> None:
        codec = RespCodec()

        payload = codec.encode_command(
            {"name": "set", "args": ["user:1", "hello", "EX", "60"]}
        )

        self.assertEqual(
            payload,
            b"*5\r\n$3\r\nSET\r\n$6\r\nuser:1\r\n$5\r\nhello\r\n$2\r\nEX\r\n$2\r\n60\r\n",
        )
        self.assertEqual(
            codec.decode_command(payload),
            {"name": "SET", "args": ["user:1", "hello", "EX", "60"]},
        )

    def test_response_roundtrip_supports_arrays_integers_and_nil(self) -> None:
        codec = RespCodec()

        payload = codec.encode_response(["2", 10, None, "ERR boom"])

        self.assertEqual(
            codec.decode_response(payload),
            ["2", 10, None, "ERR boom"],
        )

    def test_decode_response_stream_reads_single_resp_frame(self) -> None:
        codec = RespCodec()
        stream = BytesIO(b"$5\r\nhello\r\n$5\r\nlater\r\n")

        self.assertEqual(codec.decode_response_stream(stream), "hello")
        self.assertEqual(codec.decode_response_stream(stream), "later")


if __name__ == "__main__":
    unittest.main()

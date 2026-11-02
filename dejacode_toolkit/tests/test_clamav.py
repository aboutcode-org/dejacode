#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

import io
import socket
import struct
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock
from unittest.mock import patch

from dejacode_toolkit import clamav

CLAMD_ADDRESS = ("clamav", 3310)


def scan_with_clamd_response(stream, clamd_response):
    """
    Run `scan_stream` against an in-memory socket pair that replies `clamd_response`.
    Return the scan result and the bytes received on the clamd side.
    """
    client_socket, clamd_socket = socket.socketpair()
    clamd_socket.sendall(clamd_response)

    with clamd_socket:
        with patch.object(clamav, "open_connection", return_value=client_socket):
            scan_result = clamav.scan_stream(stream, CLAMD_ADDRESS)

        with clamd_socket.makefile("rb") as received_file:
            received_bytes = received_file.read()

    return scan_result, received_bytes


def make_failing_socket(send_error):
    clamd_socket = MagicMock()
    clamd_socket.sendall.side_effect = send_error
    return clamd_socket


class ClamAVTestCase(TestCase):
    @patch.object(clamav, "CHUNK_SIZE", 4)
    def test_clamav_scan_stream_sends_instream_chunks(self):
        stream = io.BytesIO(b"0123456789")
        scan_result, received_bytes = scan_with_clamd_response(stream, b"stream: OK\n")

        self.assertEqual(("OK", None), scan_result)
        expected_bytes = (
            b"nINSTREAM\n"
            + struct.pack("!L", 4)
            + b"0123"
            + struct.pack("!L", 4)
            + b"4567"
            + struct.pack("!L", 2)
            + b"89"
            + struct.pack("!L", 0)
        )
        self.assertEqual(expected_bytes, received_bytes)

    def test_clamav_scan_stream_empty_stream(self):
        stream = io.BytesIO(b"")
        scan_result, received_bytes = scan_with_clamd_response(stream, b"stream: OK\n")

        self.assertEqual(("OK", None), scan_result)
        self.assertEqual(b"nINSTREAM\n" + struct.pack("!L", 0), received_bytes)

    def test_clamav_scan_stream_found(self):
        stream = io.BytesIO(b"content")
        clamd_response = b"stream: Eicar-Test-Signature FOUND\n"
        scan_result = scan_with_clamd_response(stream, clamd_response)[0]

        self.assertEqual(("FOUND", "Eicar-Test-Signature"), scan_result)

    def test_clamav_scan_stream_size_limit_exceeded(self):
        stream = io.BytesIO(b"content")
        clamd_response = b"INSTREAM size limit exceeded. ERROR\n"

        with self.assertRaises(clamav.StreamTooLargeError):
            scan_with_clamd_response(stream, clamd_response)

    def test_clamav_scan_stream_broken_pipe(self):
        clamd_socket = make_failing_socket(BrokenPipeError)

        with patch.object(clamav, "open_connection", return_value=clamd_socket):
            with self.assertRaises(clamav.StreamTooLargeError):
                clamav.scan_stream(io.BytesIO(b"content"), CLAMD_ADDRESS)

        clamd_socket.__exit__.assert_called_once()

    def test_clamav_scan_stream_communication_error(self):
        clamd_socket = make_failing_socket(TimeoutError("timed out"))

        with patch.object(clamav, "open_connection", return_value=clamd_socket):
            with self.assertRaises(clamav.ClamdError) as context:
                clamav.scan_stream(io.BytesIO(b"content"), CLAMD_ADDRESS)

        self.assertNotIsInstance(context.exception, clamav.StreamTooLargeError)
        expected = "Communication error with clamd at ('clamav', 3310): timed out"
        self.assertEqual(expected, str(context.exception))
        clamd_socket.__exit__.assert_called_once()

    def test_clamav_scan_stream_connection_error(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            missing_socket_path = str(Path(temp_directory) / "clamd.ctl")

            with self.assertRaises(clamav.ClamdError) as context:
                clamav.scan_stream(io.BytesIO(b"content"), missing_socket_path)

        expected = f"Cannot connect to clamd at {missing_socket_path}"
        self.assertTrue(str(context.exception).startswith(expected))

    def test_clamav_parse_response(self):
        self.assertEqual(("OK", None), clamav.parse_response("stream: OK"))
        self.assertEqual(
            ("FOUND", "Win.Test.EICAR_HDB-1"),
            clamav.parse_response("stream: Win.Test.EICAR_HDB-1 FOUND"),
        )
        self.assertEqual(
            ("ERROR", "Can't allocate memory"),
            clamav.parse_response("stream: Can't allocate memory ERROR"),
        )

        with self.assertRaises(clamav.StreamTooLargeError):
            clamav.parse_response("INSTREAM size limit exceeded. ERROR")

        for unexpected_response in ["", "PONG", "stream: UNKNOWN"]:
            with self.assertRaises(clamav.ClamdError) as context:
                clamav.parse_response(unexpected_response)
            expected = f"Unexpected clamd response: {unexpected_response!r}"
            self.assertEqual(expected, str(context.exception))

    @patch("socket.create_connection")
    def test_clamav_open_connection_tcp(self, mock_create_connection):
        tcp_socket = MagicMock()
        mock_create_connection.return_value = tcp_socket

        self.assertEqual(tcp_socket, clamav.open_connection(CLAMD_ADDRESS, timeout=5))
        mock_create_connection.assert_called_once_with(CLAMD_ADDRESS, timeout=5)

    def test_clamav_open_connection_unix_socket(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            socket_path = str(Path(temp_directory) / "clamd.ctl")

            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server_socket:
                server_socket.bind(socket_path)
                server_socket.listen()

                with clamav.open_connection(socket_path, timeout=5) as unix_socket:
                    self.assertEqual(socket_path, unix_socket.getpeername())
                    self.assertEqual(5, unix_socket.gettimeout())

    def test_clamav_open_connection_unix_socket_missing(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            missing_socket_path = str(Path(temp_directory) / "clamd.ctl")

            with self.assertRaises(FileNotFoundError):
                clamav.open_connection(missing_socket_path)

#
# Copyright (c) nexB Inc. and others. All rights reserved.
# DejaCode is a trademark of nexB Inc.
# SPDX-License-Identifier: AGPL-3.0-only
# See https://github.com/aboutcode-org/dejacode for support or download.
# See https://aboutcode.org for more information about AboutCode FOSS projects.
#

"""
Minimal ClamAV client: scan a file-like object with the clamd INSTREAM command.
Standard library only, so the module can be reused outside of DejaCode.
"""

import re
import socket
import struct

DEFAULT_TCP_PORT = 3310
DEFAULT_UNIX_SOCKET_PATH = "/var/run/clamav/clamd.ctl"

# Each chunk must be smaller than the StreamMaxLength value of clamd.conf
CHUNK_SIZE = 64 * 1024

# The "n" prefix makes clamd terminate its reply with a newline
INSTREAM_COMMAND = b"nINSTREAM\n"
SIZE_LIMIT_EXCEEDED_RESPONSE = "INSTREAM size limit exceeded. ERROR"
SCAN_RESPONSE_REGEX = re.compile(r"^stream: (?:(?P<reason>.+) )?(?P<status>OK|FOUND|ERROR)$")


class ClamdError(Exception):
    pass


class StreamTooLargeError(ClamdError):
    pass


def open_connection(address, timeout=None):
    """Return a socket connected to clamd at a Unix socket path or a (host, port) tuple."""
    if not isinstance(address, str):
        return socket.create_connection(address, timeout=timeout)

    unix_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    unix_socket.settimeout(timeout)
    try:
        unix_socket.connect(address)
    except OSError:
        unix_socket.close()
        raise
    return unix_socket


def send_stream(clamd_socket, stream):
    """Send `stream` as length-prefixed chunks, ended by a zero-length chunk."""
    clamd_socket.sendall(INSTREAM_COMMAND)
    while chunk := stream.read(CHUNK_SIZE):
        clamd_socket.sendall(struct.pack("!L", len(chunk)) + chunk)
    clamd_socket.sendall(struct.pack("!L", 0))


def read_response(clamd_socket):
    with clamd_socket.makefile("rb") as response_file:
        return response_file.readline().decode("utf-8").strip()


def parse_response(response):
    """Return a (status, reason) tuple: ("OK", None), ("FOUND", signature), ("ERROR", reason)."""
    if response == SIZE_LIMIT_EXCEEDED_RESPONSE:
        raise StreamTooLargeError(response)

    response_match = SCAN_RESPONSE_REGEX.match(response)
    if not response_match:
        raise ClamdError(f"Unexpected clamd response: {response!r}")

    return response_match.group("status", "reason")


def scan_stream(stream, address, timeout=None):
    """
    Scan the `stream` file-like object with the clamd service at `address`.
    Return a (status, reason) tuple, see `parse_response`.
    """
    try:
        clamd_socket = open_connection(address, timeout)
    except OSError as error:
        raise ClamdError(f"Cannot connect to clamd at {address}: {error}") from error

    with clamd_socket:
        try:
            send_stream(clamd_socket, stream)
            response = read_response(clamd_socket)
        except BrokenPipeError as error:
            # clamd closes the connection once the stream exceeds StreamMaxLength
            raise StreamTooLargeError("Stream exceeds the clamd StreamMaxLength") from error
        except OSError as error:
            raise ClamdError(f"Communication error with clamd at {address}: {error}") from error

    return parse_response(response)

#!/usr/bin/env python3
# Copyright (c) 2019 The Bitcoin Core developers
# Distributed under the MIT software license, see the accompanying
# file COPYING or http://www.opensource.org/licenses/mit-license.php.
"""Tests NODE_COMPACT_FILTERS (BIP 157/158).

Tests that a node configured with -blockfilterindex signals NODE_COMPACT_FILTERS and responds
correctly to GET_CFILTERS, GET_CFHEADERS, GET_CFCHECKPT requests.
"""

from test_framework.messages import (
    FILTER_TYPE_BASIC,
    NODE_COMPACT_FILTERS,
    msg_getcfilters, msg_getcfheaders, msg_getcfcheckpt,
    ser_uint256, uint256_from_str, hash256,
)
from test_framework.mininode import (
    P2PInterface,
)
from test_framework.test_framework import BitcoinTestFramework
from test_framework.util import (
    assert_equal,
    connect_nodes, disconnect_nodes, sync_blocks,
    wait_until,
)

FILTER_TYPES = ["basic"]

class CFiltersClient(P2PInterface):
    def __init__(self):
        super().__init__()
        # Store the cfilters received.
        self.cfilters = []

    def pop_cfilters(self):
        cfilters = self.cfilters
        self.cfilters = []
        return cfilters

    def on_cfilter(self, message):
        """Store cfilters received in a list."""
        self.cfilters.append(message)

class CompactFiltersTest(BitcoinTestFramework):
    def set_test_params(self):
        self.setup_clean_chain = True
        self.num_nodes = 2
        self.extra_args = [
            ["-blockfilterindex", "-peercfilters"],
            ["-blockfilterindex"],
        ]

    def run_test(self):
        # Node 0 supports COMPACT_FILTERS, node 1 does not.
        node0 = self.nodes[0].add_p2p_connection(CFiltersClient())
        node1 = self.nodes[1].add_p2p_connection(CFiltersClient())

        # Nodes 0 & 1 share the same first 999 blocks in the chain.
        self.nodes[0].generate(999)
        sync_blocks(self.nodes)

        # Stale blocks by disconnecting nodes 0 & 1, mining, then reconnecting
        disconnect_nodes(self.nodes[0], 1)

        self.nodes[0].generate(1)
        wait_until(lambda: self.nodes[0].getblockcount() == 1000)
        stale_block_hash = self.nodes[0].getblockhash(1000)

        self.nodes[1].generate(1001)
        wait_until(lambda: self.nodes[1].getblockcount() == 2000)

        # Fetch cfcheckpt on node 0. Since the implementation caches the checkpoints on the active
        # chain in memory, this checks that the cache is updated correctly upon subsequent queries
        # after the reorg.
        request = msg_getcfcheckpt(
            filter_type=FILTER_TYPE_BASIC,
            stop_hash=int(stale_block_hash, 16)
        )
        node0.send_message(request)
        node0.sync_with_ping(timeout=5)
        response = node0.last_message['cfcheckpt']
        assert_equal(response.filter_type, request.filter_type)
        assert_equal(response.stop_hash, request.stop_hash)
        assert_equal(len(response.headers), 1)

        # Reorg node 0 to a new chain
        connect_nodes(self.nodes[0], 1)
        sync_blocks(self.nodes)

        main_block_hash = self.nodes[0].getblockhash(1000)
        assert main_block_hash != stale_block_hash, "node 0 chain did not reorganize"

        default_services = node1.nServices

        # Check that nodes have signalled expected services.
        assert 0 == node1.nServices & NODE_COMPACT_FILTERS
        assert_equal(node0.nServices, default_services | NODE_COMPACT_FILTERS)

        # Check that the localservices is as expected.
        assert_equal(int(self.nodes[0].getnetworkinfo()['localservices'], 16),
                     default_services | NODE_COMPACT_FILTERS)
        assert_equal(int(self.nodes[1].getnetworkinfo()['localservices'], 16),
                     default_services)

        # Check that peers can fetch cfcheckpt on active chain.
        tip_hash = self.nodes[0].getbestblockhash()
        request = msg_getcfcheckpt(
            filter_type=FILTER_TYPE_BASIC,
            stop_hash=int(tip_hash, 16)
        )
        node0.send_message(request)
        node0.sync_with_ping()
        response = node0.last_message['cfcheckpt']
        assert_equal(response.filter_type, request.filter_type)
        assert_equal(response.stop_hash, request.stop_hash)

        main_cfcheckpt = self.nodes[0].getblockfilter(main_block_hash, 'basic')['header']
        tip_cfcheckpt = self.nodes[0].getblockfilter(tip_hash, 'basic')['header']
        assert_equal(
            response.headers,
            [int(header, 16) for header in (main_cfcheckpt, tip_cfcheckpt)]
        )

        # Check that peers can fetch cfcheckpt on stale chain.
        request = msg_getcfcheckpt(
            filter_type=FILTER_TYPE_BASIC,
            stop_hash=int(stale_block_hash, 16)
        )
        node0.send_message(request)
        node0.sync_with_ping()
        response = node0.last_message['cfcheckpt']

        stale_cfcheckpt = self.nodes[0].getblockfilter(stale_block_hash, 'basic')['header']
        assert_equal(
            response.headers,
            [int(header, 16) for header in (stale_cfcheckpt,)]
        )

        # Check that peers can fetch cfheaders on active chain.
        request = msg_getcfheaders(
            filter_type=FILTER_TYPE_BASIC,
            start_height=1,
            stop_hash=int(main_block_hash, 16)
        )
        node0.send_message(request)
        node0.sync_with_ping()
        response = node0.last_message['cfheaders']
        main_cfhashes = response.hashes
        assert_equal(
            compute_last_header(response.prev_header, response.hashes),
            int(main_cfcheckpt, 16)
        )

        # Check that peers can fetch cfheaders on stale chain.
        request = msg_getcfheaders(
            filter_type=FILTER_TYPE_BASIC,
            start_height=1,
            stop_hash=int(stale_block_hash, 16)
        )
        node0.send_message(request)
        node0.sync_with_ping()
        response = node0.last_message['cfheaders']
        stale_cfhashes = response.hashes
        assert_equal(
            compute_last_header(response.prev_header, response.hashes),
            int(stale_cfcheckpt, 16)
        )

        # Check that peers can fetch cfilters.
        stop_hash = self.nodes[0].getblockhash(10)
        request = msg_getcfilters(
            filter_type=FILTER_TYPE_BASIC,
            start_height=1,
            stop_hash=int(stop_hash, 16)
        )
        node0.send_message(request)
        node0.sync_with_ping()
        response = node0.pop_cfilters()
        assert_equal(len(response), 10)

        # Check that cfilter responses are correct.
        for cfilter, cfhash, height in zip(response, main_cfhashes, range(1, 11)):
            block_hash = self.nodes[0].getblockhash(height)
            assert_equal(cfilter.filter_type, FILTER_TYPE_BASIC)
            assert_equal(cfilter.block_hash, int(block_hash, 16))
            computed_cfhash = uint256_from_str(hash256(cfilter.filter_data))
            assert_equal(computed_cfhash, cfhash)

        # Check that peers can fetch cfilters for stale blocks.
        stop_hash = self.nodes[0].getblockhash(10)
        request = msg_getcfilters(
            filter_type=FILTER_TYPE_BASIC,
            start_height=1000,
            stop_hash=int(stale_block_hash, 16)
        )
        node0.send_message(request)
        node0.sync_with_ping()
        response = node0.pop_cfilters()
        assert_equal(len(response), 1)

        cfilter = response[0]
        assert_equal(cfilter.filter_type, FILTER_TYPE_BASIC)
        assert_equal(cfilter.block_hash, int(stale_block_hash, 16))
        computed_cfhash = uint256_from_str(hash256(cfilter.filter_data))
        assert_equal(computed_cfhash, stale_cfhashes[999])

        # Requests to node 1 without NODE_COMPACT_FILTERS results in disconnection.
        requests = [
            msg_getcfcheckpt(
                filter_type=FILTER_TYPE_BASIC,
                stop_hash=int(main_block_hash, 16)
            ),
            msg_getcfheaders(
                filter_type=FILTER_TYPE_BASIC,
                start_height=1000,
                stop_hash=int(main_block_hash, 16)
            ),
            msg_getcfilters(
                filter_type=FILTER_TYPE_BASIC,
                start_height=1000,
                stop_hash=int(main_block_hash, 16)
            ),
        ]
        node1.sync_with_ping()  # ensure 'ping' has at least one message before we copy
        node1_check_message_count = dict(node1.message_count)
        node1_check_message_count['pong'] += 1
        for request in requests:
            node1.send_message(request)
        node1.sync_with_ping()
        assert_equal(node1_check_message_count, dict(node1.message_count))

        # Check that invalid requests result in disconnection.
        requests = [
            # Requesting too many filters results in disconnection.
            msg_getcfilters(
                filter_type=FILTER_TYPE_BASIC,
                start_height=0,
                stop_hash=int(main_block_hash, 16)
            ),
            # Requesting too many filter headers results in disconnection.
            msg_getcfheaders(
                filter_type=FILTER_TYPE_BASIC,
                start_height=0,
                stop_hash=int(tip_hash, 16)
            ),
            # Requesting unknown filter type results in disconnection.
            msg_getcfcheckpt(
                filter_type=255,
                stop_hash=int(main_block_hash, 16)
            ),
            # Requesting unknown hash results in disconnection.
            msg_getcfcheckpt(
                filter_type=FILTER_TYPE_BASIC,
                stop_hash=123456789,
            ),
        ]
        for request in requests:
            node0 = self.nodes[0].add_p2p_connection(CFiltersClient())
            node0.send_message(request)
            node0.wait_for_disconnect()

def compute_last_header(prev_header, hashes):
    """Compute the last filter header from a starting header and a sequence of filter hashes."""
    header = ser_uint256(prev_header)
    for filter_hash in hashes:
        header = hash256(ser_uint256(filter_hash) + header)
    return uint256_from_str(header)

if __name__ == '__main__':
    CompactFiltersTest().main()
// Copyright (c) 2009-2020 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <netaddress.h>
#include <netbase.h>

#include <string>
#include <vector>

#ifndef BITCOIN_NET_PERMISSIONS_H
#define BITCOIN_NET_PERMISSIONS_H

struct bilingual_str;

extern const std::vector<std::string> NET_PERMISSIONS_DOC;

enum NetPermissionFlags {
    PF_NONE = 0,
    // Can query bloomfilter even if -peerbloomfilters is false
    PF_BLOOMFILTER = (1U << 1),
    // Relay and accept transactions from this peer, even if -blocksonly is true
    // This peer is also not subject to limits on how many transaction INVs are tracked
    PF_RELAY = (1U << 3),
    // Always relay transactions from this peer, even if already in mempool
    // Keep parameter interaction: forcerelay implies relay
    PF_FORCERELAY = (1U << 2) | PF_RELAY,
    // Allow getheaders during IBD and block-download after maxuploadtarget limit
    PF_DOWNLOAD = (1U << 6),
    // Can't be banned/disconnected/discouraged for misbehavior
    PF_NOBAN = (1U << 4) | PF_DOWNLOAD,
    // Can query the mempool
    PF_MEMPOOL = (1U << 5),
    // Can request addrs without hitting a privacy-preserving cache
    PF_ADDR = (1U << 7),

    // Can query compact filters even if -peerblockfilters is false
    PF_BLOCKFILTERS = (1U << 8),
    // Used to avoid an error when PF_ALL is used to set PF_CFILTERS
    PF_BLOCKFILTERS_EXPLICIT = PF_BLOCKFILTERS | (1U << 9),

    // True if the user did not specifically set fine grained permissions
    PF_ISIMPLICIT = (1U << 31),
    PF_ALL = PF_BLOOMFILTER | PF_FORCERELAY | PF_RELAY | PF_NOBAN | PF_MEMPOOL | PF_DOWNLOAD | PF_ADDR | PF_BLOCKFILTERS,
};

class NetPermissions
{
public:
    NetPermissionFlags m_flags;
    static std::vector<std::string> ToStrings(NetPermissionFlags flags);
    static inline bool HasFlag(const NetPermissionFlags& flags, NetPermissionFlags f)
    {
        return (flags & f) == f;
    }
    static inline void AddFlag(NetPermissionFlags& flags, NetPermissionFlags f)
    {
        flags = static_cast<NetPermissionFlags>(flags | f);
    }
    static inline void ClearFlag(NetPermissionFlags& flags, NetPermissionFlags f)
    {
        flags = static_cast<NetPermissionFlags>(flags & ~f);
    }
};

class NetWhitebindPermissions : public NetPermissions
{
public:
    static bool TryParse(const std::string str, NetWhitebindPermissions& output, bilingual_str& error);
    CService m_service;
};

class NetWhitelistPermissions : public NetPermissions
{
public:
    static bool TryParse(const std::string str, NetWhitelistPermissions& output, ConnectionDirection& output_connection_direction, bilingual_str& error);
    static inline bool TryParse(const std::string str, NetWhitelistPermissions& output, bilingual_str& error) {
        ConnectionDirection connection_direction_ignored;
        return TryParse(str, output, connection_direction_ignored, error);
    }
    CSubNet m_subnet;
};

#endif // BITCOIN_NET_PERMISSIONS_H

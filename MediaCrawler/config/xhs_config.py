# -*- coding: utf-8 -*-
# Copyright (c) 2025 relakkes@gmail.com
#
# This file is part of MediaCrawler project.
# Repository: https://github.com/NanmiCoder/MediaCrawler/blob/main/config/xhs_config.py
# GitHub: https://github.com/NanmiCoder
# Licensed under NON-COMMERCIAL LEARNING LICENSE 1.1
#

# 声明：本代码仅供学习和研究目的使用。使用者应遵守以下原则：
# 1. 不得用于任何商业用途。
# 2. 使用时应遵守目标平台的使用条款和robots.txt规则。
# 3. 不得进行大规模爬取或对平台造成运营干扰。
# 4. 应合理控制请求频率，避免给目标平台带来不必要的负担。
# 5. 不得用于任何非法或不当的用途。
#
# 详细许可条款请参阅项目根目录下的LICENSE文件。
# 使用本代码即表示您同意遵守上述原则和LICENSE中的所有条款。


# Xiaohongshu platform configuration

# Sorting method, the specific enumeration value is in media_platform/xhs/field.py
SORT_TYPE = "popularity_descending"

# Exhaustive, bounded search controls. These are opt-in so existing collection
# commands keep their historical fixed-count behavior.
XHS_SEARCH_ALL_RESULTS = False
XHS_SEARCH_WINDOW_START = ""
XHS_SEARCH_WINDOW_END = ""
XHS_SEARCH_MAX_PAGES = 200
XHS_SEARCH_OLD_PAGE_STOP_COUNT = 2
XHS_SEARCH_PAGE_COOLDOWN_SEC = 300
XHS_SEARCH_PAGE_COOLDOWN_EVERY = 5
XHS_SEARCH_DETAIL_SESSION_LIMIT = 8
XHS_SEARCH_PAGE_SESSION_LIMIT = 0
XHS_SEARCH_CARD_ONLY = False

# Specify the note URL list, which must carry the xsec_token parameter
XHS_SPECIFIED_NOTE_URL_LIST = [
    "https://www.xiaohongshu.com/explore/64b95d01000000000c034587?xsec_token=AB0EFqJvINCkj6xOCKCQgfNNh8GdnBC_6XecG4QOddo3Q=&xsec_source=pc_cfeed"
    # ........................
]

# Specify the creator URL list, which needs to carry xsec_token and xsec_source parameters.

XHS_CREATOR_ID_LIST = [
    "https://www.xiaohongshu.com/user/profile/5f58bd990000000001003753?xsec_token=ABYVg1evluJZZzpMX-VWzchxQ1qSNVW3r-jOEnKqMcgZw=&xsec_source=pc_search"
    # ........................
]

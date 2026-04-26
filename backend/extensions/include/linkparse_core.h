#pragma once
#include <string>
#include <tuple>
#include <vector>

using LinkMatch = std::tuple<std::string, std::string, std::string, int, int>;

std::vector<LinkMatch> find_urls(const std::string &raw_bbcode);

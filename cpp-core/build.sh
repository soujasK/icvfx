#!/usr/bin/env bash
# Builds the Sprint 1 C++20 core: packet_generator + kinematic_engine.
set -euo pipefail
cd "$(dirname "$0")"

mkdir -p bin
CXXFLAGS="-std=c++20 -O2 -Wall -Wextra -Wno-unused-parameter -pthread"

echo "[build] packet_generator"
g++ $CXXFLAGS -o bin/packet_generator src/packet_generator.cpp

echo "[build] kinematic_engine"
g++ $CXXFLAGS -o bin/kinematic_engine src/kinematic_engine.cpp

echo "[build] ok -> cpp-core/bin/{packet_generator,kinematic_engine}"

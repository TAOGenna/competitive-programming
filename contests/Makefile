CXX = g++-16
CXXFLAGS = -std=c++23 -O2 -Wall
# Sample runs only: trace() on, and a 256MB stack like Codeforces (macOS gives 8MB).
TESTFLAGS = -DDEBUG -Wl,-stack_size,0x10000000
# Seconds before a sample run is killed and reported as TLE.
TL = 5

CP := $(dir $(abspath $(lastword $(MAKEFILE_LIST))))
export CXX CXXFLAGS TESTFLAGS TL

# Goals are phony so an existing .cpp or contest folder always reruns.
.PHONY: help $(MAKECMDGOALS)
help:
	@python3 "$(CP)cp.py" help

# `make code.cpp` -> ./code.
$(filter %.cpp,$(MAKECMDGOALS)):
	$(CXX) $(CXXFLAGS) $@ -o $(basename $@)

# `make cf2268` / `make abc370` -> contest folder. `make A` -> run A.cpp on its samples.
$(filter-out help %.cpp,$(MAKECMDGOALS)):
	@python3 "$(CP)cp.py" $@ || true

#define LISA_POWER_HOST_TEST
#include "../overlays/lisa_power_compat.c"
#include <assert.h>
#include <limits.h>
#include <stdio.h>

int main(void)
{
    bool (*debug_fn)(void) = power_debug_print_enabled;
    ssize_t (*capacity_fn)(ssize_t) = mi_power_save_battery_cave;
    unsigned int mode;
    ssize_t cap, last, actual, expected;
    assert(!debug_fn());
    lisa_power_debug_enable = true;
    assert(debug_fn());
    lisa_power_debug_enable = false;
    for (mode = 0; mode < 5; ++mode) {
        assert(lisa_power_mode_valid(mode));
        lisa_power_mode = mode;
        last = -1;
        for (cap = 0; cap <= 100; ++cap) {
            actual = capacity_fn(cap);
            expected = cap;
            if (mode >= 2) {
                expected = cap > 20 ? ((cap - 20) * 100 + 106) / 107 + 25 :
                                      (cap * 100 + 79) / 80;
                if (expected > 100) expected = 100;
            }
            assert(actual == expected && actual >= last);
            assert(actual >= 0 && actual <= 100);
            last = actual;
        }
        assert(capacity_fn(-1) == -1);
        assert(capacity_fn(LONG_MIN) == LONG_MIN);
        assert(capacity_fn(LONG_MAX) == LONG_MAX);
        assert(capacity_fn(101) == 101);
    }
    assert(!lisa_power_mode_valid(5));
    assert(!lisa_power_mode_valid(ULONG_MAX));
    puts("LISA0056_POWER_HOST_TEST=PASS (505 normal inputs plus invalid bounds)");
    return 0;
}

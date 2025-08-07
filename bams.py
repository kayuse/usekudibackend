def can_jump(nums):
    max_reach = 0
    print("Starting to evaluate jumps...")
    print(f"Initial max reach: {max_reach}")
    for i, jump in enumerate(nums):
        print(f"At index {i}, jump value: {jump}, current max reach: {max_reach}")
        if i > max_reach:
            print("Failed to reach this index.")
            return False  # stuck before reaching this point
        max_reach = max(max_reach, i + jump)
        print(f"Updated max reach: {max_reach}")
    print("Successfully evaluated all jumps.")
    return True

# Test
print(can_jump([2, 3, 1, 1, 4]))  # True
#print(can_jump([3, 2, 1, 0, 4])) 
#pragma once

// A queue between exactly two threads: one only pushes, the other only pops. Neither ever waits for
// the other (no lock), which is what lets the audio callback use it.
//
// Coming from C#: there is no garbage collector to make a lock-free structure easy, and no
// ConcurrentQueue in the standard library. This one works because each index is written by one
// thread only; the atomics make each side see a consistent value of the other's index.

#include <atomic>
#include <cstddef>
#include <vector>

namespace korre
{

template <typename T>
class spsc_queue
{
public:
    /// Room for at least `capacity` items (rounded up to a power of two).
    explicit spsc_queue(std::size_t capacity)
    {
        std::size_t size = 2;
        while (size < capacity)
        {
            size <<= 1;
        }
        slots_.resize(size);
        mask_ = size - 1;
    }

    // ---- the producer's side

    /// The slot the next push will fill, or nullptr if the queue is full. Fill it, then call push().
    T* back() noexcept
    {
        const std::size_t tail = tail_.load(std::memory_order_relaxed);
        if (tail - head_.load(std::memory_order_acquire) > mask_)
        {
            return nullptr;
        }
        return &slots_[tail & mask_];
    }
    void push() noexcept { tail_.store(tail_.load(std::memory_order_relaxed) + 1, std::memory_order_release); }

    // ---- the consumer's side

    /// The oldest item, or nullptr if the queue is empty. Use it, then call pop().
    T* front() noexcept
    {
        const std::size_t head = head_.load(std::memory_order_relaxed);
        if (head == tail_.load(std::memory_order_acquire))
        {
            return nullptr;
        }
        return &slots_[head & mask_];
    }
    void pop() noexcept { head_.store(head_.load(std::memory_order_relaxed) + 1, std::memory_order_release); }

    // ---- either side

    /// Items waiting. Exact for the thread that asks only in the direction it cannot change itself.
    std::size_t size() const noexcept { return tail_.load(std::memory_order_acquire) - head_.load(std::memory_order_acquire); }
    std::size_t capacity() const noexcept { return mask_ + 1; }

private:
    std::vector<T> slots_;
    std::size_t mask_ = 0;
    // On separate cache lines, so the two threads do not slow each other down by sharing one.
    alignas(64) std::atomic<std::size_t> head_{0};
    alignas(64) std::atomic<std::size_t> tail_{0};
};

} // namespace korre

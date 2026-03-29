# Questions And Answers

## Q. Why is `SET` much slower than `GET` in this Mini Redis?

`SET` is slower because it does much more work than `GET` in the current implementation.

`GET` mainly:

- checks whether the key expired
- looks up the value in the in-memory storage

`SET` does all of these:

- writes the value into the in-memory storage
- advances incremental rehashing when resizing is in progress
- starts a new resize when the load factor exceeds the threshold
- updates TTL metadata
- updates invalidation tag metadata when tags are provided
- appends the operation to AOF persistence
- checks autosave and AOF rewrite scheduling conditions

So the current structure is not just `read` versus `write`.

It is closer to:

- `GET = lookup`
- `SET = write + metadata update + persistence`

That is why `SET` can appear significantly slower than `GET`, especially when:

- rehashing is active
- many new keys are being inserted
- AOF append overhead is included

## Q. Is this behavior abnormal?

No. In the current Mini Redis, this is expected behavior.

The project intentionally keeps `SET` on the full write path, while `GET` stays relatively lightweight.

## Q. What is likely the biggest reason for the gap?

The main reasons are:

- storage write and resize logic
- AOF persistence append
- extra metadata work such as TTL and invalidation handling

If you want to analyze it more precisely later, the next step would be to measure these separately:

- pure storage time
- persistence time
- total request time

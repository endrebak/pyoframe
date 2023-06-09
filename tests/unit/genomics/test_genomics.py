import polars as pl

from poranges.ops import merge

df = pl.DataFrame(
    {
        "chrom": [1, 2, 1, 1],
        "starts": [4, 10, 7, 1],
        "ends": [5, 11, 8, 6],
        "weights": [-42, 0, 2, 1],
    }
)


def test_merge_intervals():
    res = merge(df.lazy(), "starts", "ends", by=["chrom"]).collect()

    res.frame_equal(
        pl.DataFrame(
            [
                pl.Series("starts", [[1, 7], [10]], dtype=pl.List(pl.Int64)),
                pl.Series("ends", [[6, 8], [11]], dtype=pl.List(pl.Int64)),
                pl.Series("chrom", [[1, 1, 1], [2]], dtype=pl.List(pl.Int64)),
                pl.Series("cluster_ids", [[0, 0, 1], [0]], dtype=pl.List(pl.Int64)),
                pl.Series("starts_before_merge", [[1, 4, 7], [10]], dtype=pl.List(pl.Int64)),
                pl.Series("ends_before_merge", [[6, 5, 8], [11]], dtype=pl.List(pl.Int64)),
                pl.Series("weights", [[1, -42, 2], [0]], dtype=pl.List(pl.Int64)),
            ]
        )
    )


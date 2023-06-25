from typing import List

import polars as pl

STARTS_PROPERTY = "starts"
ENDS_PROPERTY = "ends"
STARTS2_PROPERTY = "starts_2"
ENDS2_PROPERTY = "ends_2"

STARTS_2IN1_PROPERTY = "starts_2in1"
ENDS_2IN1_PROPERTY = "ends_2in1"
STARTS_1IN2_PROPERTY = "starts_1in2"
ENDS_1IN2_PROPERTY = "ends_1in2"
MASK_1IN2_PROPERTY = "mask_1in2"
MASK_2IN1_PROPERTY = "mask_2in1"
LENGTHS_2IN1_PROPERTY = "lengths_2in1"
LENGTHS_1IN2_PROPERTY = "lengths_1in2"


def search(col1: str, col2: str, side: str = "left") -> pl.Expr:
    return pl.col(col1).explode().search_sorted(pl.col(col2).explode(), side=side)


def lengths(starts: str, ends: str, outname: str = "") -> pl.Expr:
    return pl.col(ends).explode().sub(pl.col(starts).explode()).explode().alias(outname)


def find_starts_in_ends(
    starts, ends, starts_2, ends_2, closed: bool = False
) -> List[pl.Expr]:
    side = "right" if closed else "left"

    return [
        search(starts_2, starts, side="left").alias(STARTS_2IN1_PROPERTY).implode(),
        search(starts_2, ends, side=side).alias(ENDS_2IN1_PROPERTY).implode(),
        search(starts, starts_2, side="right").alias(STARTS_1IN2_PROPERTY).implode(),
        search(starts, ends_2, side=side).alias(ENDS_1IN2_PROPERTY).implode(),
    ]


def compute_masks() -> List[pl.Expr]:
    return [
        pl.all(),
        pl.col(ENDS_2IN1_PROPERTY)
        .explode()
        .gt(pl.col(STARTS_2IN1_PROPERTY).explode())
        .implode()
        .alias(MASK_2IN1_PROPERTY),
        pl.col(ENDS_1IN2_PROPERTY)
        .explode()
        .gt(pl.col(STARTS_1IN2_PROPERTY).explode())
        .implode()
        .alias(MASK_1IN2_PROPERTY),
    ]


def apply_masks() -> List[pl.Expr]:
    return [
        pl.exclude(
            STARTS_1IN2_PROPERTY,
            STARTS_2IN1_PROPERTY,
            ENDS_1IN2_PROPERTY,
            ENDS_2IN1_PROPERTY,
        ),
        pl.col([STARTS_2IN1_PROPERTY, ENDS_2IN1_PROPERTY])
        .explode()
        .filter(pl.col(MASK_2IN1_PROPERTY).explode())
        .implode(),
        pl.col([STARTS_1IN2_PROPERTY, ENDS_1IN2_PROPERTY])
        .explode()
        .filter(pl.col(MASK_1IN2_PROPERTY).explode())
        .implode(),
    ]


def add_length(starts: str, ends: str, alias: str) -> pl.Expr:
    return (
        pl.col(ends)
        .explode()
        .sub(pl.col(starts).explode())
        .alias(alias)
        .implode()
    )


def add_lengths() -> List[pl.Expr]:
    return (
        [
            pl.all(),
            add_length(STARTS_2IN1_PROPERTY, ENDS_2IN1_PROPERTY, LENGTHS_2IN1_PROPERTY),
            add_length(STARTS_1IN2_PROPERTY, ENDS_1IN2_PROPERTY, LENGTHS_1IN2_PROPERTY)
        ]
    )


def repeat_frame(columns, startsin, endsin) -> pl.Expr:
    return (
        pl.col(columns)
        .explode()
        .repeat_by(pl.col(endsin).explode() - pl.col(startsin).explode())
        .explode()
    )


def mask_and_repeat_frame(columns, mask, startsin, endsin) -> pl.Expr:
    return (
        pl.col(columns)
        .explode()
        .filter(pl.col(mask).explode())
        .repeat_by(pl.col(endsin).explode() - pl.col(startsin).explode())
        .explode()
    )


def repeat_other(columns, starts, diffs):
    return (
        pl.col(columns)
        .explode()
        .take(
            arange_multi(diffs=diffs, starts=starts)
        )
    )


def arange_multi(*, starts: pl.Expr, diffs: pl.Expr) -> pl.Expr:
    return (
        starts.filter(diffs.gt(0))
        .explode()
        .repeat_by(diffs.explode().filter(diffs.explode().gt(0)))
        .explode()
        .add(
            pl.arange(0, diffs.explode().sum())
            .explode()
            .sub(
                diffs.filter(diffs.gt(0))
                .explode()
                .cumsum()
                .sub(diffs.explode().filter(diffs.gt(0)))
                .repeat_by(diffs.explode().filter(diffs.gt(0)))
                .explode()
            )
        )
    )


def join(
    df: pl.LazyFrame,
    df2: pl.LazyFrame,
    suffix: str,
    starts: str,
    ends: str,
    starts_2: str,
    ends_2: str,
) -> pl.LazyFrame:
    sorted_collapsed = df.sort(starts, ends).select([pl.all().implode()])
    sorted_collapsed_2 = df2.sort(starts_2, ends_2).select([pl.all().implode()])
    j = sorted_collapsed.join(sorted_collapsed_2, how="cross", suffix=suffix)

    df_2_column_names_after_join = j.columns[len(df.columns) :]
    starts_2_renamed = df_2_column_names_after_join[df2.columns.index(starts_2)]
    ends_2_renamed = df_2_column_names_after_join[df2.columns.index(ends_2)]

    return (
        j.with_columns(
            find_starts_in_ends(starts, ends, starts_2_renamed, ends_2_renamed)
        )
        .with_columns(compute_masks())
        .with_columns(apply_masks())
        .with_columns(add_lengths())
        .select(
            pl.concat(
                [
                    mask_and_repeat_frame(
                        df.columns,
                        MASK_2IN1_PROPERTY,
                        STARTS_2IN1_PROPERTY,
                        ENDS_2IN1_PROPERTY,
                    ),
                    repeat_other(
                        df.columns, pl.col(STARTS_1IN2_PROPERTY).explode(), pl.col(LENGTHS_1IN2_PROPERTY).explode()
                    ),
                ]
            ),
            pl.concat(
                [
                    repeat_other(
                        df_2_column_names_after_join,
                        pl.col(STARTS_2IN1_PROPERTY).explode(),
                        pl.col(LENGTHS_2IN1_PROPERTY).explode(),
                    ),
                    mask_and_repeat_frame(
                        df_2_column_names_after_join,
                        MASK_1IN2_PROPERTY,
                        STARTS_1IN2_PROPERTY,
                        ENDS_1IN2_PROPERTY,
                    ),
                ]
            ),
        )
    )


def overlap(
    df: pl.LazyFrame,
    df2: pl.LazyFrame,
    starts: str,
    ends: str,
    starts_2: str,
    ends_2: str,
) -> pl.LazyFrame:
    sorted_collapsed = df.sort(starts, ends).select([pl.all().implode()])
    sorted_collapsed_2 = df2.sort(starts_2, ends_2).select([pl.all().implode()])
    j = sorted_collapsed.join(sorted_collapsed_2, how="cross")

    df_2_column_names_after_join = j.columns[len(df.columns) :]
    starts_2_renamed = df_2_column_names_after_join[df2.columns.index(starts_2)]
    ends_2_renamed = df_2_column_names_after_join[df2.columns.index(ends_2)]

    return (
        j.with_columns(
            find_starts_in_ends(starts, ends, starts_2_renamed, ends_2_renamed)
        )
        .with_columns(compute_masks())
        .select(pl.all())
        .select(
            pl.col(df.columns).explode().filter(pl.col(MASK_2IN1_PROPERTY).explode())
        )
    )

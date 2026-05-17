## Revenge games — top 10 players, card-table with headshots.
## Two flavors:
##   flavor = "recent"  → vs a team they played for in 2024 or 2025 (recent move)
##   flavor = "drafted" → vs the team that drafted them (career-long revenge)

source("/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026/scripts/viz_r/_theme.R")

flavor <- Sys.getenv("REVENGE_FLAVOR", unset = "recent")
stopifnot(flavor %in% c("recent", "drafted"))

input_file <- if (flavor == "drafted") "data_drafted.parquet" else "data.parquet"
output_file <- if (flavor == "drafted") "table_drafted.png" else "table.png"
title_text <- if (flavor == "drafted") {
  "Top 10 revenge games · vs the team that drafted them"
} else {
  "Top 10 revenge games · vs a recent former team"
}
subtitle_text <- if (flavor == "drafted") {
  "Skill-position players facing the franchise that originally drafted them in 2026."
} else {
  "Skill-position players facing a team they played for in 2024 or 2025."
}

rev <- read_parquet(file.path(PROJ_ROOT, "output/revenge_games", input_file))
val <- read_parquet("/Users/nick/projects/dynasty-dashboard/data/merged.parquet") |>
  dplyr::select(name, position, blended_value, age)

norm <- function(s) gsub("[^a-z]", "", tolower(s))
rev$nname <- norm(rev$player_name)
val$nname <- norm(val$name)

# Inner-join to dynasty rankings (we use value for ranking, but won't display it)
joined <- rev |>
  dplyr::inner_join(val, by = c("nname", "position"))

# Top 10 unique players (a player might have multiple revenge weeks vs same team —
# collapse to one row per player, listing all weeks)
top10 <- joined |>
  dplyr::group_by(player_name) |>
  dplyr::summarise(
    position    = dplyr::first(position),
    current_team = dplyr::first(current_team),
    former_team  = dplyr::first(former_team),
    age          = dplyr::first(age),
    years_exp    = dplyr::first(years_exp),
    blended_value = dplyr::first(blended_value),
    weeks        = paste(sort(unique(revenge_week)), collapse = ", "),
    n_meetings   = dplyr::n_distinct(revenge_week),
    .groups = "drop"
  ) |>
  dplyr::arrange(dplyr::desc(blended_value)) |>
  dplyr::slice_head(n = 10) |>
  dplyr::mutate(rank = dplyr::row_number())

# Resolve gsis_id for headshots
gsis <- resolve_gsis(top10$player_name, position = top10$position,
                     team = top10$current_team)
top10$gsis_id <- gsis$gsis_id

# Position colors
pos_pal <- c(QB = "#274690", RB = "#1f6f43", WR = "#a17a1f", TE = "#7a3b9b")
top10$pos_col <- pos_pal[top10$position]

# Column x positions (units arbitrary; we'll set fixed scale)
COL <- list(
  rank      = 0.02,
  headshot  = 0.10,
  name      = 0.18,
  pos       = 0.50,
  current   = 0.60,
  arrow     = 0.66,
  former    = 0.72,
  weeks     = 0.83
)

# y-axis: rank 1 at TOP -> reverse y
top10$y <- -top10$rank

p <- ggplot(top10) +
  # alternating row backgrounds
  geom_rect(aes(xmin = -0.01, xmax = 1.01,
                ymin = y - 0.45, ymax = y + 0.45),
            fill = ifelse(top10$rank %% 2 == 0, "#efe9dc", "#f5f1ea"),
            colour = NA) +
  # rank
  geom_text(aes(x = COL$rank, y = y, label = sprintf("%02d", rank)),
            family = "mono", fontface = "bold", size = 7,
            colour = PAL$muted, hjust = 0) +
  # headshot
  nflplotR::geom_nfl_headshots(
    aes(player_gsis = gsis_id, y = y), x = COL$headshot,
    height = 0.085, na.rm = TRUE
  ) +
  # name + age
  geom_text(aes(x = COL$name, y = y + 0.10, label = player_name),
            fontface = "bold", size = 5.3, colour = PAL$ink, hjust = 0) +
  geom_text(aes(x = COL$name, y = y - 0.15,
                label = sprintf("age %.0f  ·  %s yrs exp",
                                age,
                                ifelse(is.na(years_exp), "—",
                                       as.character(as.integer(years_exp))))),
            size = 3.7, colour = PAL$muted, hjust = 0) +
  # position chip
  geom_label(aes(x = COL$pos, y = y, label = position),
             fill = top10$pos_col, colour = "white",
             fontface = "bold", size = 4.0,
             label.size = 0, label.padding = unit(0.25, "lines"),
             label.r = unit(0.18, "lines")) +
  # current team logo
  nflplotR::geom_nfl_logos(
    aes(team_abbr = current_team, y = y), x = COL$current,
    width = 0.035
  ) +
  # arrow
  geom_text(aes(x = COL$arrow, y = y, label = "vs"),
            family = "serif", fontstyle = "italic", size = 4.5,
            colour = PAL$muted, hjust = 0.5) +
  # former team logo
  nflplotR::geom_nfl_logos(
    aes(team_abbr = former_team, y = y), x = COL$former,
    width = 0.035
  ) +
  # weeks
  geom_text(aes(x = COL$weeks, y = y + 0.10, label = sprintf("Week %s", weeks)),
            fontface = "bold", size = 4.6, colour = PAL$ink, hjust = 0) +
  geom_text(aes(x = COL$weeks, y = y - 0.15,
                label = ifelse(n_meetings == 1, "1 meeting", sprintf("%d meetings", n_meetings))),
            size = 3.5, colour = PAL$muted, hjust = 0) +
  scale_x_continuous(limits = c(-0.01, 1.01), expand = expansion(0)) +
  scale_y_continuous(expand = expansion(add = c(0.6, 0.6))) +
  labs(
    title = title_text,
    subtitle = subtitle_text,
    caption = "Data: nflverse 2024/2025/2026 rosters · headshots & logos: nflplotR"
  ) +
  theme_void(base_size = 13) +
  theme(
    plot.background  = element_rect(fill = PAL$bg, colour = NA),
    panel.background = element_rect(fill = PAL$bg, colour = NA),
    plot.title       = element_textbox_simple(size = 22, face = "bold",
                          colour = PAL$ink, margin = margin(b = 8), lineheight = 1.1),
    plot.subtitle    = element_textbox_simple(size = 13, colour = PAL$muted,
                          margin = margin(b = 18), lineheight = 1.35),
    plot.caption     = element_text(size = 9, colour = PAL$muted,
                          hjust = 0, margin = margin(t = 12)),
    plot.caption.position = "plot",
    plot.title.position = "plot",
    plot.margin = margin(20, 28, 14, 28)
  )

save_chart(p, file.path(PROJ_ROOT, "output/revenge_games", output_file),
           width = 16, height = 12)

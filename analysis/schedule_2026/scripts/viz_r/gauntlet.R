## Gauntlet — per-team-per-week tile heatmap of opponent tier.

source("/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026/scripts/viz_r/_theme.R")

games <- read.csv(file.path(PROJ_ROOT, "data/raw/games.csv"), stringsAsFactors = FALSE) |>
  dplyr::filter(season == 2026)

win_totals <- read.csv(file.path(PROJ_ROOT, "data/raw/win_totals_2026.csv"),
                       stringsAsFactors = FALSE)

# Long table: (team, week, opp) — join opponent's win total
home <- data.frame(team = games$home_team, week = games$week, opp = games$away_team)
away <- data.frame(team = games$away_team, week = games$week, opp = games$home_team)
tw <- rbind(home, away)
all_teams <- sort(unique(c(home$team, away$team)))
weeks <- sort(unique(tw$week))
grid <- expand.grid(team = all_teams, week = weeks, stringsAsFactors = FALSE)
tw <- merge(grid, tw, by = c("team", "week"), all.x = TRUE)
tw <- merge(tw, win_totals[, c("team", "win_total")],
            by.x = "opp", by.y = "team", all.x = TRUE)
tw$is_bye <- is.na(tw$opp)

# Percentile-rank each opponent's win total within the 32 teams (0-100, ties averaged)
win_totals$opp_pct <- rank(win_totals$win_total, ties.method = "average") /
                     nrow(win_totals) * 100
tw <- merge(tw, win_totals[, c("team", "opp_pct")],
            by.x = "opp", by.y = "team", all.x = TRUE)

# Sort teams: hardest schedule (highest avg opponent win total) at top
team_avg <- aggregate(win_total ~ team, data = tw, FUN = mean, na.rm = TRUE)
team_order <- team_avg$team[order(team_avg$win_total)]

tw$team  <- factor(tw$team, levels = team_order)
tw$label <- ifelse(tw$is_bye, "BYE", tw$opp)

# Split: byes use a separate fill (constant black), opponent games use gradient
opp_layer <- tw[!tw$is_bye, ]
bye_layer <- tw[tw$is_bye, ]

p <- ggplot() +
  # opponent cells colored by percentile within league
  geom_tile(data = opp_layer,
            aes(x = week, y = team, fill = opp_pct),
            colour = "white", linewidth = 0.5) +
  # bye cells in black
  geom_tile(data = bye_layer,
            aes(x = week, y = team),
            fill = PAL$ink, colour = "white", linewidth = 0.5) +
  # opponent labels: light text on dark ends, dark text in the middle
  geom_text(data = opp_layer,
            aes(x = week, y = team, label = label,
                colour = opp_pct > 75 | opp_pct < 25),
            size = 3.2, fontface = "bold") +
  geom_text(data = bye_layer,
            aes(x = week, y = team, label = label),
            colour = "white", size = 3.0, fontface = "bold") +
  scale_fill_gradientn(
    name   = "Opponent quality (percentile within league)",
    colours = c("#2c5fa7", "#7fb3d5", "#f5f1ea", "#e6a392", "#c8553d"),
    values  = scales::rescale(c(0, 25, 50, 75, 100)),
    limits  = c(0, 100),
    breaks  = c(0, 25, 50, 75, 100),
    labels  = c("weakest", "25", "median", "75", "toughest"),
    guide   = guide_colourbar(barwidth = 22, barheight = 0.55,
                              title.position = "top", title.hjust = 0.5)
  ) +
  scale_colour_manual(
    values = c(`TRUE` = "white", `FALSE` = "#1a1a1a"),
    guide = "none"
  ) +
  scale_x_continuous(breaks = weeks, expand = expansion(0)) +
  scale_y_discrete(expand = expansion(0)) +
  labs(
    title    = "2026 schedule gauntlets: opponent quality by team & week",
    subtitle = paste0(
      "Each cell colored by the opponent's percentile rank within the 32-team league by Vegas win total. ",
      "<span style='color:#a23b3b'><b>Red</b></span> = top-tier opponents, ",
      "<span style='color:#2c5fa7'><b>blue</b></span> = bottom-tier, neutral = mid. ",
      "<b>Black</b> = bye. Teams sorted by avg opponent quality (hardest schedule at top)."
    ),
    x        = "Week",
    y        = NULL,
    caption  = "Data: 2026 schedule × DraftKings win totals · logos: nflplotR"
  ) +
  coord_cartesian(clip = "off") +
  theme_sched(13) +
  theme(
    axis.text.y         = nflplotR::element_nfl_logo(size = 0.9),
    axis.ticks          = element_blank(),
    panel.grid          = element_blank(),
    legend.position     = "top"
  )

save_chart(p, file.path(PROJ_ROOT, "output/gauntlet/chart.png"),
           width = 18, height = 12)

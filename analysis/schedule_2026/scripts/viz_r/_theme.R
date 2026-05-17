## Shared theme, helpers, palettes for the schedule_2026 R viz suite.

suppressPackageStartupMessages({
  library(ggplot2)
  library(dplyr)
  library(nflplotR)
  library(nflreadr)
  library(arrow)
  library(scales)
  library(ggtext)
  library(stringi)
  library(forcats)
  library(ggrepel)
})

# ---- project paths -------------------------------------------------------
PROJ_ROOT <- "/Users/nick/projects/dynasty-dashboard/analysis/schedule_2026"

# ---- palettes ------------------------------------------------------------
PAL <- list(
  ink       = "#1a1a1a",
  text      = "#1d1d1f",
  muted     = "#6b6f76",
  grid      = "#dcdfe4",
  bg        = "#ffffff",
  panel     = "#fafbfc",
  pos       = "#1f6f43",   # green (advantage)
  neg       = "#a23b3b",   # red (disadvantage)
  neutral   = "#94a3b8",
  accent    = "#274690",
  warm      = "#d97706",
  cool      = "#1d4ed8",
  diverge_lo = "#1d4ed8",
  diverge_mi = "#f4f4f5",
  diverge_hi = "#a23b3b",
  tier_top  = "#a23b3b",
  tier_mid  = "#cbd2da",
  tier_bot  = "#1d4ed8",
  tier_bye  = "#1a1a1a"
)

# ---- base theme ----------------------------------------------------------
# Use theme_bw as base because theme_minimal interacts poorly with
# nflplotR::element_nfl_logo (removes axis lines that the logo grob references).
theme_sched <- function(base_size = 13) {
  theme_bw(base_size = base_size, base_family = "") %+replace%
    theme(
      plot.background     = element_rect(fill = PAL$bg, colour = NA),
      panel.background    = element_rect(fill = PAL$bg, colour = NA),
      panel.border        = element_blank(),
      axis.line.x         = element_line(colour = PAL$grid, linewidth = 0.4),
      axis.line.y         = element_line(colour = PAL$grid, linewidth = 0.4),
      axis.ticks          = element_line(colour = PAL$grid, linewidth = 0.4),
      axis.ticks.length   = unit(3, "pt"),
      panel.grid.major.x  = element_line(colour = PAL$grid, linewidth = 0.3),
      panel.grid.major.y  = element_line(colour = PAL$grid, linewidth = 0.3),
      panel.grid.minor    = element_blank(),
      plot.title          = element_textbox_simple(
                              size = base_size + 6, face = "bold",
                              colour = PAL$ink,
                              margin = margin(b = 6), lineheight = 1.15),
      plot.subtitle       = element_textbox_simple(
                              size = base_size, colour = PAL$muted,
                              margin = margin(b = 12), lineheight = 1.3),
      plot.caption        = element_text(size = base_size - 3,
                                         colour = PAL$muted, hjust = 0,
                                         margin = margin(t = 10)),
      plot.caption.position = "plot",
      plot.title.position = "plot",
      axis.title.x        = element_text(size = base_size, colour = PAL$text,
                                         margin = margin(t = 8)),
      axis.title.y        = element_text(size = base_size, colour = PAL$text,
                                         margin = margin(r = 8)),
      axis.text.x         = element_text(size = base_size - 1, colour = PAL$text),
      legend.position     = "top",
      legend.title        = element_text(size = base_size - 1, colour = PAL$text),
      legend.text         = element_text(size = base_size - 1, colour = PAL$text),
      legend.background   = element_rect(fill = PAL$bg, colour = NA),
      legend.key          = element_rect(fill = PAL$bg, colour = NA),
      strip.text          = element_text(size = base_size, face = "bold",
                                         colour = PAL$ink,
                                         margin = margin(b = 4, t = 4)),
      strip.background    = element_rect(fill = PAL$panel, colour = NA),
      plot.margin         = margin(18, 22, 14, 18)
    )
}

# ---- save wrapper --------------------------------------------------------
save_chart <- function(plot, path, width = 16, height = 12, dpi = 160) {
  dir <- dirname(path)
  if (!dir.exists(dir)) dir.create(dir, recursive = TRUE)
  ggsave(
    filename = path,
    plot     = plot,
    width    = width,
    height   = height,
    dpi      = dpi,
    units    = "in",
    bg       = PAL$bg,
    device   = ragg::agg_png
  )
  size <- file.info(path)$size
  message(sprintf("[ok] %s  (%.1f KB)", path, size / 1024))
  invisible(path)
}

# ---- roster / headshot helpers ------------------------------------------
ROSTER_CACHE <- new.env(parent = emptyenv())

load_rosters_local <- function() {
  if (!is.null(ROSTER_CACHE$r)) return(ROSTER_CACHE$r)
  path <- file.path(PROJ_ROOT, "data/raw/rosters_2025.csv")
  r <- read.csv(path, stringsAsFactors = FALSE)
  # also attach league-wide nflreadr roster for 2025 — wider coverage of gsis_ids
  more <- tryCatch(nflreadr::load_rosters(2025), error = function(e) NULL)
  if (!is.null(more)) {
    keep <- c("full_name", "first_name", "last_name", "team", "position", "gsis_id", "headshot_url")
    more <- more[, intersect(keep, names(more)), drop = FALSE]
    r <- dplyr::bind_rows(
      r[, intersect(names(r), c("full_name", "first_name", "last_name",
                                "team", "position", "gsis_id", "headshot_url")),
        drop = FALSE],
      more
    )
  }
  r <- r |>
    dplyr::filter(!is.na(full_name), nchar(full_name) > 0) |>
    dplyr::mutate(
      norm = name_norm(full_name)
    ) |>
    dplyr::distinct(norm, position, .keep_all = TRUE)
  ROSTER_CACHE$r <- r
  r
}

name_norm <- function(x) {
  x <- stringi::stri_trans_general(x, "Any-Latin; Latin-ASCII")
  x <- tolower(x)
  # Strip apostrophes WITHOUT introducing a space (so "Ja'Quan" -> "jaquan", matching PFR)
  x <- gsub("['`’]", "", x)
  x <- gsub("[^a-z0-9 ]+", " ", x)
  x <- gsub("\\b(jr|sr|ii|iii|iv|v)\\b", " ", x)
  x <- gsub("\\s+", " ", x)
  trimws(x)
}

#' Resolve player gsis_id by name+position(+team).
#' Returns a tibble with cols: input_name, gsis_id, headshot_url, matched (logical)
resolve_gsis <- function(player_name, position = NULL, team = NULL) {
  r <- load_rosters_local()
  out <- data.frame(
    input_name = player_name,
    position   = if (!is.null(position)) position else NA_character_,
    team       = if (!is.null(team)) team else NA_character_,
    gsis_id    = NA_character_,
    headshot_url = NA_character_,
    matched    = FALSE,
    stringsAsFactors = FALSE
  )
  out$norm <- name_norm(out$input_name)
  for (i in seq_len(nrow(out))) {
    cand <- r
    if (!is.na(out$position[i])) cand <- cand[cand$position == out$position[i] | is.na(cand$position), , drop = FALSE]
    if (!is.na(out$team[i]))     cand <- cand[is.na(cand$team) | cand$team == out$team[i], , drop = FALSE]
    hit <- cand[cand$norm == out$norm[i], , drop = FALSE]
    if (nrow(hit) == 0) {
      # try without position filter
      hit <- r[r$norm == out$norm[i], , drop = FALSE]
    }
    if (nrow(hit) > 0) {
      # prefer rows that have a gsis_id
      hit <- hit[order(is.na(hit$gsis_id) | hit$gsis_id == ""), , drop = FALSE]
      out$gsis_id[i] <- hit$gsis_id[1]
      out$headshot_url[i] <- if ("headshot_url" %in% names(hit)) hit$headshot_url[1] else NA_character_
      out$matched[i] <- !is.na(out$gsis_id[i]) && nzchar(out$gsis_id[i])
    }
  }
  out$norm <- NULL
  out
}

# ---- ordered team factor (by some metric) -------------------------------
team_factor_by <- function(team, metric, decreasing = TRUE) {
  ord <- order(metric, decreasing = decreasing, na.last = TRUE)
  factor(team, levels = team[ord])
}

# ---- common annotation: league average rule line ------------------------
hline_avg <- function(y, label = "league avg") {
  list(
    geom_hline(yintercept = y, linetype = "31", colour = PAL$muted, linewidth = 0.5),
    annotate("text", x = Inf, y = y, label = label,
             hjust = 1.05, vjust = -0.5,
             colour = PAL$muted, size = 3.4, family = "")
  )
}
vline_avg <- function(x, n_rows = NULL, label = "league avg") {
  y_pos <- if (is.null(n_rows)) Inf else n_rows + 0.8
  vjust <- if (is.null(n_rows)) 1.2 else 0.5
  list(
    geom_vline(xintercept = x, linetype = "31", colour = PAL$muted, linewidth = 0.5),
    annotate("text", x = x, y = y_pos, label = label,
             hjust = -0.05, vjust = vjust,
             colour = PAL$muted, size = 3.4, family = "")
  )
}

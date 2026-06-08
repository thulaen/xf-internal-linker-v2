//! `xftool` — the single Rust command-line multi-tool (ADR 0008).
//!
//! One binary, many grouped subcommands (`xftool <group> <verb-noun>`). This is
//! tooling, not app architecture: the Django app and the kernel crates never
//! depend on it. Every subcommand obeys the contract in
//! `docs/specs/fr-rust-cli-tooling.md`: read-only by default, `--format
//! json|table|csv`, and CI exit codes `0` ok / `1` findings / `2` error.

mod catalog;
mod commands;
mod output;
mod util;

use clap::{Parser, Subcommand};

use output::{Format, ToolReport};
use util::ToolError;

/// Top-level CLI: a global `--format` plus one subcommand group.
#[derive(Parser, Debug)]
#[command(
    name = "xftool",
    version,
    about = "Repo CLI multi-tool: CI checks, log forensics, data cleanup, auditing.",
    long_about = "xftool is the single Rust command-line multi-tool for this repo \
(ADR 0008). One binary, many grouped subcommands. Read-only by default; mutating \
tools require --apply. Output format is selectable with --format; exit codes are \
0 ok / 1 findings / 2 error."
)]
struct Cli {
    /// Output format for the result.
    #[arg(long, value_enum, default_value_t = Format::Table, global = true)]
    format: Format,

    #[command(subcommand)]
    command: Command,
}

/// The subcommand groups. Each variant delegates to a module in [`commands`].
#[derive(Subcommand, Debug)]
enum Command {
    /// Print the catalog of available subcommands.
    List {
        /// Only show subcommands whose category contains this text.
        #[arg(long)]
        category: Option<String>,
    },
    /// Ranking-run validity tools.
    #[command(subcommand)]
    Ranking(commands::ranking::RankingCmd),
    /// Score-breakdown validity tools.
    #[command(subcommand)]
    Score(commands::score::ScoreCmd),
    /// Artifact integrity tools.
    #[command(subcommand)]
    Artifact(commands::artifact::ArtifactCmd),
    /// Search-index manifest audit tools.
    #[command(subcommand)]
    Index(commands::index::IndexCmd),
    /// Benchmark output tools.
    #[command(subcommand)]
    Bench(commands::bench::BenchCmd),
    /// Weight-profile lint tools.
    #[command(subcommand)]
    Weights(commands::weights::WeightsCmd),
    /// Log forensics tools.
    #[command(subcommand)]
    Log(commands::log::LogCmd),
    /// Compiled-artifact store tools.
    #[command(subcommand)]
    Store(commands::store::StoreCmd),
}

impl Command {
    /// Dispatch to the selected subcommand. Every arm returns a [`ToolReport`];
    /// `main` renders it once with the chosen format and exits with its code.
    fn run(&self) -> Result<ToolReport, ToolError> {
        match self {
            Self::List { category } => Ok(catalog::list_report(category.as_deref())),
            Self::Ranking(c) => c.run(),
            Self::Score(c) => c.run(),
            Self::Artifact(c) => c.run(),
            Self::Index(c) => c.run(),
            Self::Bench(c) => c.run(),
            Self::Weights(c) => c.run(),
            Self::Log(c) => c.run(),
            Self::Store(c) => c.run(),
        }
    }
}

fn main() {
    let cli = Cli::parse();
    let exit = match cli.command.run() {
        Ok(report) => {
            print!("{}", report.render(cli.format));
            report.exit
        }
        Err(err) => {
            eprintln!("FAIL xftool: {err}");
            err.code
        }
    };
    std::process::exit(exit as i32);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cli_parses_list_subcommand() {
        let cli = Cli::try_parse_from(["xftool", "list"]).unwrap();
        assert!(matches!(cli.command, Command::List { category: None }));
        assert_eq!(cli.format, Format::Table);
    }

    #[test]
    fn global_format_flag_parses_json() {
        let cli = Cli::try_parse_from(["xftool", "--format", "json", "list"]).unwrap();
        assert_eq!(cli.format, Format::Json);
    }

    #[test]
    fn ranking_diff_requires_two_paths() {
        assert!(Cli::try_parse_from(["xftool", "ranking", "diff", "only-one"]).is_err());
        assert!(Cli::try_parse_from(["xftool", "ranking", "diff", "a.json", "b.json"]).is_ok());
    }

    #[test]
    fn list_run_returns_ok_report() {
        let cmd = Command::List { category: None };
        let report = cmd.run().unwrap();
        assert_eq!(report.exit, output::ExitCode::Ok);
        assert!(!report.rows.is_empty());
    }

    #[test]
    fn unknown_subcommand_is_rejected() {
        assert!(Cli::try_parse_from(["xftool", "bogus"]).is_err());
    }
}

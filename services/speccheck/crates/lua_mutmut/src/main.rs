//! Docker-managed LuaJIT mutation runner.

#![forbid(unsafe_code)]
#![allow(clippy::pedantic, clippy::nursery, clippy::cargo)]
use std::env;
use std::ffi::OsStr;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use mlua::Lua;

#[derive(Debug, Clone)]
struct Config {
    report: PathBuf,
    helper: PathBuf,
    tests: Vec<PathBuf>,
    sources: Vec<PathBuf>,
}

#[derive(Debug, Clone)]
struct Mutant {
    kind: &'static str,
    source: PathBuf,
    description: String,
    mutated_text: String,
}

#[derive(Debug, Default)]
struct MutationSummary {
    total: usize,
    killed: usize,
    survived: usize,
    timeout: usize,
    unviable: usize,
    score: f64,
    survived_details: Vec<String>,
    timeout_details: Vec<String>,
}

fn main() {
    if env::args().any(|arg| arg == "--version") {
        println!("lua-mutmut 0.1.0");
        return;
    }
    let config = match parse_args(env::args().skip(1).collect()) {
        Ok(value) => value,
        Err(error) => {
            eprintln!("{error}");
            std::process::exit(2);
        }
    };

    let summary = match run(config) {
        Ok(value) => value,
        Err(error) => {
            eprintln!("FAIL lua-mutmut: {error}");
            std::process::exit(2);
        }
    };
    if summary.survived > 0 || summary.timeout > 0 {
        std::process::exit(1);
    }
}

fn parse_args(args: Vec<String>) -> Result<Config, String> {
    let mut report = None;
    let mut helper = None;
    let mut tests = Vec::new();
    let mut sources = Vec::new();
    let mut index = 0;
    while index < args.len() {
        match args[index].as_str() {
            "--report" => {
                index += 1;
                report = args.get(index).map(PathBuf::from);
            }
            "--helper" => {
                index += 1;
                helper = args.get(index).map(PathBuf::from);
            }
            "--test" => {
                index += 1;
                if let Some(path) = args.get(index) {
                    tests.push(PathBuf::from(path));
                }
            }
            "--" => {
                sources.extend(args[index + 1..].iter().map(PathBuf::from));
                break;
            }
            other => sources.push(PathBuf::from(other)),
        }
        index += 1;
    }

    let config = Config {
        report: report.ok_or(
            "usage: lua-mutmut --report <path> --helper <path> --test <spec> -- <source.lua>...",
        )?,
        helper: helper.ok_or("--helper is required")?,
        tests,
        sources,
    };
    if config.tests.is_empty() {
        return Err("at least one --test file is required".to_string());
    }
    if config.sources.is_empty() {
        return Err("at least one source file is required after --".to_string());
    }
    Ok(config)
}

fn run(config: Config) -> Result<MutationSummary, String> {
    let mut summary = MutationSummary::default();
    for source in &config.sources {
        let text = fs::read_to_string(source)
            .map_err(|error| format!("{} could not be read: {error}", source.display()))?;
        for mutant in generate_mutants(source, &text) {
            summary.total += 1;
            match run_mutant(&config, &mutant)? {
                MutantResult::Killed => summary.killed += 1,
                MutantResult::Survived => {
                    summary.survived += 1;
                    summary.survived_details.push(mutant.description.clone());
                }
                MutantResult::Timeout => {
                    summary.timeout += 1;
                    summary.timeout_details.push(mutant.description.clone());
                }
                MutantResult::Unviable => summary.unviable += 1,
            }
        }
    }
    let viable = summary.total.saturating_sub(summary.unviable);
    summary.score = if viable == 0 {
        100.0
    } else {
        (summary.killed as f64 / viable as f64) * 100.0
    };
    write_report(&config.report, &summary)?;
    println!(
        "lua-mutmut: total={} killed={} survived={} timeout={} unviable={} score={:.2}",
        summary.total,
        summary.killed,
        summary.survived,
        summary.timeout,
        summary.unviable,
        summary.score
    );
    for survived in &summary.survived_details {
        eprintln!("SURVIVED {survived}");
    }
    Ok(summary)
}

fn generate_mutants(source: &Path, text: &str) -> Vec<Mutant> {
    let mut mutants = Vec::new();
    for (kind, from, to) in [
        ("boolean_flip", "true", "false"),
        ("boolean_flip", "false", "true"),
        ("comparison_flip", " ~= ", " == "),
        ("comparison_flip", " == ", " ~= "),
        ("comparison_flip", " <= ", " < "),
        ("comparison_flip", " >= ", " > "),
        ("arithmetic_flip", " + ", " - "),
        ("arithmetic_flip", " - ", " + "),
        ("arithmetic_flip", " * ", " / "),
        ("arithmetic_flip", " / ", " * "),
        ("numeric_boundary", " 0", " 1"),
        ("numeric_boundary", " 1", " 0"),
        ("return_nil", "return {", "return nil --[[mutated]] {"),
    ] {
        mutants.extend(replace_each(source, text, kind, from, to));
    }
    mutants.extend(empty_string_mutants(source, text));
    mutants
}

fn replace_each(
    source: &Path,
    text: &str,
    kind: &'static str,
    from: &str,
    to: &str,
) -> Vec<Mutant> {
    let mut mutants = Vec::new();
    let mut offset = 0;
    while let Some(position) = text[offset..].find(from) {
        let start = offset + position;
        let end = start + from.len();
        let mut mutated = String::with_capacity(text.len() + to.len());
        mutated.push_str(&text[..start]);
        mutated.push_str(to);
        mutated.push_str(&text[end..]);
        mutants.push(Mutant {
            kind,
            source: source.to_path_buf(),
            description: format!("{}:{}:{}:{}->{}", source.display(), start, kind, from, to),
            mutated_text: mutated,
        });
        offset = end;
    }
    mutants
}

fn empty_string_mutants(source: &Path, text: &str) -> Vec<Mutant> {
    let bytes = text.as_bytes();
    let mut mutants = Vec::new();
    let mut index = 0;
    while index < bytes.len() {
        if bytes[index] != b'"' {
            index += 1;
            continue;
        }
        let start = index;
        index += 1;
        let mut escaped = false;
        while index < bytes.len() {
            let byte = bytes[index];
            if escaped {
                escaped = false;
            } else if byte == b'\\' {
                escaped = true;
            } else if byte == b'"' {
                break;
            }
            index += 1;
        }
        if index >= bytes.len() {
            break;
        }
        let end = index + 1;
        if end > start + 2 {
            let mut mutated = String::with_capacity(text.len());
            mutated.push_str(&text[..start]);
            mutated.push_str("\"\"");
            mutated.push_str(&text[end..]);
            mutants.push(Mutant {
                kind: "empty_string",
                source: source.to_path_buf(),
                description: format!("{}:{}:empty_string:literal->empty", source.display(), start),
                mutated_text: mutated,
            });
        }
        index = end;
    }
    mutants
}

enum MutantResult {
    Killed,
    Survived,
    Timeout,
    Unviable,
}

fn run_mutant(config: &Config, mutant: &Mutant) -> Result<MutantResult, String> {
    if compile_lua(&mutant.mutated_text).is_err() {
        return Ok(MutantResult::Unviable);
    }
    let root = create_workspace()?;
    copy_runtime_tree(&root, config)?;
    write_mutant(&root, mutant)?;
    let result = Command::new("timeout")
        .arg("30")
        .arg("busted")
        .arg("--helper")
        .arg(&config.helper)
        .args(&config.tests)
        .current_dir(&root)
        .output();
    let _ = fs::remove_dir_all(&root);
    match result {
        Ok(output) if output.status.success() => Ok(MutantResult::Survived),
        Ok(output) if output.status.code() == Some(124) => Ok(MutantResult::Timeout),
        Ok(_) => Ok(MutantResult::Killed),
        Err(error) => Err(format!("could not run busted for {}: {error}", mutant.kind)),
    }
}

fn compile_lua(text: &str) -> mlua::Result<()> {
    let lua = Lua::new();
    let _chunk = lua.load(text).set_name("mutant").into_function()?;
    Ok(())
}

fn create_workspace() -> Result<PathBuf, String> {
    let millis = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or(Duration::from_secs(0))
        .as_millis();
    let path = env::temp_dir().join(format!("xf-lua-mutmut-{}-{millis}", std::process::id()));
    fs::create_dir_all(&path)
        .map_err(|error| format!("could not create temp workspace: {error}"))?;
    Ok(path)
}

fn copy_runtime_tree(root: &Path, config: &Config) -> Result<(), String> {
    let mut paths = config.tests.clone();
    paths.push(config.helper.clone());
    for source in &config.sources {
        paths.push(source.clone());
    }
    for path in paths {
        copy_one(&path, root)?;
    }
    copy_fixture_dirs(root)
}

fn copy_fixture_dirs(root: &Path) -> Result<(), String> {
    for dir in [
        "apps/governance/lua_runtime/advisors/tests/fixtures",
        "frontend/nginx-lua/tests",
    ] {
        let path = Path::new(dir);
        if path.exists() {
            copy_dir(path, &root.join(path))?;
        }
    }
    Ok(())
}

fn copy_one(path: &Path, root: &Path) -> Result<(), String> {
    let target = root.join(path);
    if let Some(parent) = target.parent() {
        fs::create_dir_all(parent)
            .map_err(|error| format!("could not create {}: {error}", parent.display()))?;
    }
    fs::copy(path, &target)
        .map_err(|error| format!("could not copy {}: {error}", path.display()))?;
    Ok(())
}

fn copy_dir(source: &Path, target: &Path) -> Result<(), String> {
    fs::create_dir_all(target)
        .map_err(|error| format!("could not create {}: {error}", target.display()))?;
    for entry in fs::read_dir(source)
        .map_err(|error| format!("could not read {}: {error}", source.display()))?
    {
        let entry = entry.map_err(|error| format!("could not read dir entry: {error}"))?;
        let from = entry.path();
        let to = target.join(entry.file_name());
        if from.is_dir() {
            copy_dir(&from, &to)?;
        } else if from.extension() == Some(OsStr::new("lua"))
            || from.extension() == Some(OsStr::new("json"))
        {
            fs::copy(&from, &to)
                .map_err(|error| format!("could not copy {}: {error}", from.display()))?;
        }
    }
    Ok(())
}

fn write_mutant(root: &Path, mutant: &Mutant) -> Result<(), String> {
    let target = root.join(&mutant.source);
    fs::write(&target, &mutant.mutated_text)
        .map_err(|error| format!("could not write mutant {}: {error}", target.display()))
}

fn write_report(path: &Path, summary: &MutationSummary) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| {
            format!("could not create report dir {}: {error}", parent.display())
        })?;
    }
    let json = format!(
        "{{\"total\":{},\"killed\":{},\"survived\":{},\"timeout\":{},\"unviable\":{},\"score\":{:.2},\"survived_details\":{},\"timeout_details\":{}}}\n",
        summary.total,
        summary.killed,
        summary.survived,
        summary.timeout,
        summary.unviable,
        summary.score,
        json_array(&summary.survived_details),
        json_array(&summary.timeout_details)
    );
    fs::write(path, json).map_err(|error| format!("could not write report: {error}"))
}

fn json_array(values: &[String]) -> String {
    let items = values
        .iter()
        .map(|value| format!("\"{}\"", value.replace('\\', "\\\\").replace('"', "\\\"")))
        .collect::<Vec<_>>()
        .join(",");
    format!("[{items}]")
}

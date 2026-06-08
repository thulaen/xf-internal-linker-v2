//! Fast scoped LuaJIT sandbox and dialect checker.

#![forbid(unsafe_code)]
#![allow(clippy::pedantic, clippy::nursery, clippy::cargo)]
use std::env;
use std::fs;
use std::path::{Path, PathBuf};

use mlua::Lua;

#[derive(Debug, Clone, Copy)]
struct ForbiddenPattern {
    label: &'static str,
    token: &'static str,
}

const FORBIDDEN: &[ForbiddenPattern] = &[
    ForbiddenPattern {
        label: "io",
        token: "io.",
    },
    ForbiddenPattern {
        label: "os",
        token: "os.",
    },
    ForbiddenPattern {
        label: "debug",
        token: "debug.",
    },
    ForbiddenPattern {
        label: "require",
        token: "require(",
    },
    ForbiddenPattern {
        label: "loadfile",
        token: "loadfile(",
    },
    ForbiddenPattern {
        label: "dofile",
        token: "dofile(",
    },
];

const DIALECT_FORBIDDEN: &[ForbiddenPattern] = &[
    ForbiddenPattern {
        label: "Lua 5.3 integer division",
        token: "//",
    },
    ForbiddenPattern {
        label: "Lua 5.4 close attribute",
        token: "<close>",
    },
    ForbiddenPattern {
        label: "Lua 5.3 utf8 library",
        token: "utf8.",
    },
];

fn main() {
    let paths = env::args().skip(1).map(PathBuf::from).collect::<Vec<_>>();
    if paths.is_empty() {
        eprintln!("usage: lua-fastcheck <file.lua> [more.lua ...]");
        std::process::exit(2);
    }

    let failures = paths
        .iter()
        .flat_map(|path| check_file(path))
        .collect::<Vec<_>>();

    if !failures.is_empty() {
        for failure in failures {
            eprintln!("{failure}");
        }
        std::process::exit(1);
    }
}

fn check_file(path: &Path) -> Vec<String> {
    let mut failures = Vec::new();
    let text = match fs::read_to_string(path) {
        Ok(value) => value,
        Err(error) => {
            return vec![format!(
                "LuaUnavailableError: {} could not be read: {error}",
                path.display()
            )];
        }
    };

    failures.extend(check_tokens(
        path,
        &text,
        FORBIDDEN,
        "LuaSandboxViolationError",
    ));
    failures.extend(check_tokens(
        path,
        &text,
        DIALECT_FORBIDDEN,
        "LuaDialectViolationError",
    ));
    if let Err(error) = compile_lua(path, &text) {
        failures.push(format!(
            "LuaUnavailableError: {} failed LuaJIT parse: {error}",
            path.display()
        ));
    }
    failures
}

fn check_tokens(
    path: &Path,
    text: &str,
    patterns: &[ForbiddenPattern],
    error_type: &str,
) -> Vec<String> {
    patterns
        .iter()
        .filter(|pattern| text.contains(pattern.token))
        .map(|pattern| format!("{error_type}: {} uses {}", path.display(), pattern.label))
        .collect()
}

fn compile_lua(path: &Path, text: &str) -> mlua::Result<()> {
    let lua = Lua::new();
    let _chunk = lua
        .load(text)
        .set_name(path.to_string_lossy())
        .into_function()?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{check_file, check_tokens, FORBIDDEN};
    use std::fs;

    #[test]
    fn flags_forbidden_host_access() {
        let failures = check_tokens(
            std::path::Path::new("example.lua"),
            "return io.read()",
            FORBIDDEN,
            "LuaSandboxViolationError",
        );

        assert_eq!(failures.len(), 1);
        assert!(failures[0].contains("LuaSandboxViolationError"));
    }

    #[test]
    fn accepts_simple_luajit_chunk() {
        let dir = std::env::temp_dir();
        let path = dir.join("lua_fastcheck_simple.lua");
        fs::write(&path, "local value = 1\nreturn value\n").unwrap();

        assert!(check_file(&path).is_empty());

        let _ = fs::remove_file(path);
    }
}

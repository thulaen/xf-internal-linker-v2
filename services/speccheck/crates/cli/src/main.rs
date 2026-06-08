//! Command-line entry point for speccheck.
//!
//! The initial binary prints the canonical empty report while detector and
//! parser subcommands are wired slice by slice.

#![forbid(unsafe_code)]
#![allow(clippy::pedantic, clippy::nursery, clippy::cargo)]
fn main() {
    let args: Vec<String> = std::env::args().collect();
    if let Err(error) = speccheck::run(&args) {
        eprintln!("FAIL speccheck: {error}");
        std::process::exit(2);
    }
}

//! Subcommand groups for `xftool`.
//!
//! Each module owns one group (`xftool <group> <verb-noun>`). Adding a verb to a
//! group is a few lines: a new `Subcommand` variant + a `match` arm + one
//! [`crate::catalog::CATALOG`] row. Adding a whole group is one module here plus
//! one variant in [`crate::Cli`].

pub mod artifact;
pub mod bench;
pub mod index;
pub mod log;
pub mod ranking;
pub mod score;
pub mod store;
pub mod weights;

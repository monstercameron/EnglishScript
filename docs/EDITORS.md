# EnglishScript in an editor

EnglishScript comes with a language server and a rename tool. The server lets an editor that speaks the Language Server Protocol mark problems as you write, offer corrections, and find where a name is defined. Both are plain Python with no dependencies, like the compiler.

The server has been run and tested on Windows with Python 3.12, by the test suite, which drives it directly and also starts it as a separate program and talks to it over pipes. It has not been run inside Neovim, Helix or VS Code. The configurations below for Neovim and Helix are written from those editors' documentation and are untested.

## What the server does

- **Problems.** Every problem the linter finds is marked in the text, with its message, its advice and the rule to remember. An error is an error; a suggestion is a warning. Where the reference teaches the rule, the problem links to that section.
- **Corrections.** When the linter is certain how to mend a problem, the correction is offered as a quick fix, titled `Mend:` and the corrected line. When there are two or more, `Mend all that can be mended` applies them together.
- **Hover.** Over a sentence the compiler read, the notes that `--explain` prints: what `its` meant, which definition a word led to. A mistake on another line does not hide them. Over a name, the sentence that defines it. Over a line with a problem, the problem.
- **Outline.** The kinds (with their properties), sets of choices (with their choices), things, adjectives, verbs, worked-out values, top-level variables and reactions of the file.
- **Go to definition.** From a name to the sentence that defines it, in the same file or in a chapter the file uses. From a `Use the ... chapter` sentence, to the chapter's file.
- **Suggestions.** At the start of a line, the sentence forms (`Say`, `Let the ... be`, `If ...:`, `To ...:` and the rest) and the file's own verbs. After `'s`, `its` or `whose`, the properties. Elsewhere, the names that can be said there.
- **Unsaved chapters.** A chapter that is open in the editor is read as it stands there, saved or not, for all of the above. Changing it marks the open files that use it again.
- **Rename.** Renames a name throughout the file, and refuses if the result would read any worse than what was there. See "The rename tool" below.

## Starting it

```bash
python -m englishscript.server
```

It reads messages on standard input and answers on standard output, and writes nothing else there. Anything it has to say about itself goes to standard error. Run by hand, it will simply wait: it is meant to be started by an editor.

Python must be able to find the `englishscript` package. It is not installed anywhere by default, so either start the server from the repository's folder, or set `PYTHONPATH` to that folder. The configurations below set `PYTHONPATH`; change `/path/to/EnglishScript` to where the repository is.

## The file type

EnglishScript programs are files ending in `.english`. No editor knows that ending, so each configuration below teaches it. Indent with spaces: the language refuses tabs. The examples use two spaces. Comments start with `#`.

## Neovim

An untested configuration, written from Neovim's documentation for its built-in LSP client (`vim.filetype.add` and `vim.lsp.start`, Neovim 0.8 or later). Put it in `init.lua`:

```lua
vim.filetype.add({ extension = { english = "englishscript" } })

vim.api.nvim_create_autocmd("FileType", {
  pattern = "englishscript",
  callback = function(args)
    vim.bo[args.buf].expandtab = true
    vim.bo[args.buf].shiftwidth = 2
    vim.bo[args.buf].commentstring = "# %s"
    vim.lsp.start({
      name = "englishscript",
      cmd = { "python", "-m", "englishscript.server" },
      cmd_env = { PYTHONPATH = "/path/to/EnglishScript" },
      root_dir = vim.fs.dirname(vim.api.nvim_buf_get_name(args.buf)),
    })
  end,
})
```

## Helix

An untested configuration, written from Helix's documentation for `languages.toml`. Put it in `~/.config/helix/languages.toml` (on Windows, `%AppData%\helix\languages.toml`):

```toml
[language-server.englishscript]
command = "python"
args = ["-m", "englishscript.server"]
environment = { PYTHONPATH = "/path/to/EnglishScript" }

[[language]]
name = "englishscript"
scope = "source.englishscript"
file-types = ["english"]
comment-token = "#"
indent = { tab-width = 2, unit = "  " }
language-servers = ["englishscript"]
```

## VS Code

VS Code does not start a language server from its settings. It needs a small extension that declares the `.english` file type and starts `python -m englishscript.server`. That extension has not been written, so the server cannot be used from VS Code today. The [playground](https://monstercameron.github.io/EnglishScript/playground.html) marks and corrects a program in the browser without it.

## The rename tool

```bash
python -m englishscript.rename examples/dragons.english "dragon" "wyrm"
python -m englishscript.rename examples/dragons.english "dragon" "wyrm" --write
```

The first prints the program with the name changed. With `--write` it rewrites the file instead. The editor's rename command does the same through the server.

What it changes:

- Every whole occurrence of the name outside quoted text, and inside the `{fill-ins}` of quoted text. Capitals don't matter, so `smaug` is found where `Smaug` was defined. Each occurrence keeps its own capitals where they differed from the definition, so a verb that starts a sentence stays capitalised.
- For a kind, its plural too: `dragon` to `wyrm` also turns `dragons` into `wyrms`. A plural that was stated where the kind was described (`A child (plural children) has ...`) is kept when the kind is renamed, and can be renamed itself (`children` to `bairns`).
- `a` and `an` in front of the name, where the linter says the new name needs the other one.
- A name of several words is matched whole, and a longer name that contains it is left alone: renaming `month` does not touch `month row`. A leading `the` is ignored, so `"the month row"` and `"month row"` name the same thing.
- Names in any alphabet, as the language allows them: `Fáfnir`, `Größe`. Capitals are folded as the compiler folds them. Where an occurrence's capitals would not fold back to the new name (`MASS` is not `Maß`), the new name is written there as you gave it.

What it refuses, changing nothing, with status 1 and the reason on standard error:

- a name that is not defined in the file (if a chapter the file uses defines it, the message says which). A name counts as defined when the compiler read the sentence that defines it, so a name whose own sentence is refused cannot be renamed until that sentence is mended;
- a new name that is a reserved word or contains one;
- a new name that is already in use, in the file or in a chapter or library it uses;
- a thing whose name is also looked for in quotes (`the dragon called "Smaug"`), because quoted text is never changed;
- **anything the linter likes less afterwards.** The result is linted, and if it has a problem the original did not, the rename is refused and the message gives that problem.

A word that is both a verb and something else (the language allows a verb to share its word with a name) is renamed as both. `--only verb` or `--only name` renames one of them. The editor's rename picks by where the cursor is. In the editor, a name that belongs to one block (a role with its own name, a loop's name, a variable made inside) is renamed in that block only; the command renames it in every block of the file.

## What it does not do

- **No colouring.** There is no grammar for syntax highlighting, for any editor.
- **One file at a time.** A rename changes the file it is given. Renaming a word that a chapter shares does not change the files that use the chapter; they will be marked with problems until they are changed too.
- **Checked by reading, not by running.** A rename is checked by the linter, which compiles and runs nothing. Quoted text is not changed, so a `Say` or a `For example` that spells the old name out in quotes will still say the old name.
- **A name whose sentence is refused is not in the outline.** The outline, the definitions and the suggestions come from the compiler's own table of names, which holds what its readable sentences define. Three things the table leaves out are read from the text instead, by the form of the sentence: the name a loop gives its thing (`For each rival in dragons:`), `Whenever everything has settled:`, and the words of a library. If the compiler cannot give its table at all, everything is read from the text that way, and can then be wrong about a sentence the compiler refuses.
- **Suggestions are not checked against types.** Every name that could be said at that place is offered, not only those that would fit.
- **A chapter changed outside the editor is noticed late.** A chapter that is not open is read from the disk when a file that uses it is next changed or saved in the editor, not at the moment it changes.
- **A library's words can be suggested and hovered, but not gone to.** They are defined inside the library's Python file, and the compiler's table of names does not list them.
- **No formatting, find references, signature help, workspace symbols or semantic tokens.**
- **The whole text is sent and linted on every change.** On the computer this was written on, linting any example in this repository took under a twentieth of a second, apart from the first use of a library, and the table of names behind the outline and the suggestions took as long again. Open files that use chapters are linted again when any other open file changes. The server does not wait for a pause in typing; that is left to the editor.
- **Positions are counted in UTF-16**, which every editor supports; the server does not offer another encoding.

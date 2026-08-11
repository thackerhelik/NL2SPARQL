# Fuseki Server Setup

This folder contains the scripts to host our local Pokemon Knowledge Graph.
Before running the python setup script, **you must install Apache Jena and Fuseki** and add them to your system path.

## 1. Prerequisites
* **Java 17 or higher** is required.
  * Check with: `java -version`
  * If missing, install OpenJDK (e.g., via [Eclipse Temurin](https://adoptium.net/)).

---

## 2. Installation Guide

### macOS / Linux

1. **Download the tools:**
   * Go to the [Apache Jena Downloads](https://jena.apache.org/download/index.cgi).
   * Download the **Binary** distributions (zip or tar.gz) for:
     * `apache-jena-5.6.0` (The core tools)
     * `apache-jena-fuseki-5.6.0` (The server)
2. **Extract them:**
   * Unzip both files to a folder (e.g., `~/jena/`).
3. **Update your PATH:**
   * Add the `bin` folders to your shell profile (`~/.zshrc` or `~/.bashrc`).
   * Add these lines (adjust the path to where you unzipped):
     ```bash
     export PATH=$PATH:~/jena/apache-jena-5.6.0/bin
     export PATH=$PATH:~/jena/apache-jena-fuseki-5.6.0
     ```
4. **Apply changes:**
   * Run `source ~/.zshrc` (or restart terminal).
5. **Run the provided script:**
   * Run the provided setup_pokemon.py script to set up the knowledge graph (Ensure that schema folder is also present alongside fuseki folder)

### Windows

1. **Download the tools:**
   * Go to the [Apache Jena Downloads](https://jena.apache.org/download/index.cgi).
   * Download the **Binary** `.zip` files for both **Apache Jena** and **Apache Jena Fuseki**.
2. **Extract them:**
   * Unzip them to a permanent location (e.g., `C:\Tools\Jena\` and `C:\Tools\Fuseki\`).
3. **Update System Environment Variables:**
   * Press `Win` key and search for **"Edit the system environment variables"**.
   * Click **Environment Variables**.
   * Under System variables, click New… and add:
        * JENA_HOME = C:\Tools\Jena\apache-jena-5.6.0
        * FUSEKI_HOME = C:\Tools\Fuseki\apache-jena-fuseki-5.6.0
   * Under **System variables**, find `Path` and click **Edit**.
   * Click **New** and add the path to the **bat folder** %JENA_HOME%\bat
   * Click **New** and add the path %FUSEKI_HOME%
   * Click **OK** to save.
4. **Run the provided script:**
   * Run the provided setup_pokemon.py script to set up the knowledge graph (Ensure that schema folder is also present alongside fuseki folder)

## Troubleshooting

### Linux/macOS: `fuseki-server: Permission denied`
If you unpacked the Fuseki archive and the scripts are not executable, run from the Fuseki directory:
```bash
chmod +x fuseki-server
```
Then retry ```fuseki-server --help```

### Windows: ClassNotFoundException when running fuseki-server.bat
On Windows, fuseki-server.bat relies on files in the Fuseki distribution directory. If you run it from a different folder, it may fail to find its JAR/classpath.

Recommended: run Fuseki via the provided Python setup script (it sets the working directory to %FUSEKI_HOME%).

If starting manually: ```cd /d "%FUSEKI_HOME%"``` then run ```fuseki-server.bat --help```


### Reference documentation
- Fuseki (current): https://jena.apache.org/documentation/fuseki2/fuseki-quick-start.html
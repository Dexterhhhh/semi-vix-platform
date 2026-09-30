// svix-package exports reviewed source files, never a working directory snapshot.
package main

import (
	"archive/tar"
	"bytes"
	"compress/gzip"
	"crypto/sha256"
	"encoding/hex"
	"flag"
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"time"
)

type exporter struct {
	root       string
	files      map[string][]byte
	executable map[string]bool
}

func (e *exporter) add(source, target string) error {
	info, err := os.Lstat(filepath.Join(e.root, source))
	if err != nil {
		return err
	}
	if !info.Mode().IsRegular() {
		return fmt.Errorf("non-regular source file: %s", source)
	}
	data, err := os.ReadFile(filepath.Join(e.root, source))
	if err != nil {
		return err
	}
	e.files[target] = data
	return nil
}
func (e *exporter) tree(dir string, extensions map[string]bool) error {
	return filepath.WalkDir(filepath.Join(e.root, dir), func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		relative, err := filepath.Rel(e.root, path)
		if err != nil {
			return err
		}
		relative = filepath.ToSlash(relative)
		if d.Type()&os.ModeSymlink != 0 {
			return fmt.Errorf("symbolic link in source tree: %s", relative)
		}
		if d.IsDir() {
			if strings.HasPrefix(d.Name(), ".") || relative == "go/cmd/svix-package" {
				return filepath.SkipDir
			}
			return nil
		}
		if extensions[filepath.Ext(path)] {
			return e.add(relative, relative)
		}
		return nil
	})
}
func credentials(root string) [][]byte {
	data, err := os.ReadFile(filepath.Join(root, ".env"))
	if err != nil {
		return nil
	}
	names := map[string]bool{"SECRET_KEY": true, "SECRET_ENCRYPTION_KEY": true, "CREDENTIAL_MASTER_KEY": true, "SVIX_ADMIN_USERNAME": true, "SVIX_ADMIN_PASSWORD": true, "POSTGRES_PASSWORD": true, "ALPACA_API_KEY": true, "ALPACA_API_SECRET": true}
	var result [][]byte
	for _, line := range strings.Split(string(data), "\n") {
		name, value, ok := strings.Cut(line, "=")
		if ok && names[strings.TrimSpace(name)] {
			value = strings.Trim(strings.TrimSpace(value), "\"'")
			if len(value) >= 8 && !strings.HasPrefix(value, "replace_") {
				result = append(result, []byte(value))
			}
		}
	}
	return result
}
func audit(files map[string][]byte, private [][]byte, edition string) error {
	email := regexp.MustCompile(`[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}`)
	for name, data := range files {
		if strings.HasPrefix(name, "/") || strings.Contains(name, "..") {
			return fmt.Errorf("invalid archive path")
		}
		if edition == "alpaca" && (strings.HasSuffix(name, ".py") || strings.HasPrefix(name, "backend/")) {
			return fmt.Errorf("Python source in Alpaca edition")
		}
		if bytes.Contains(data, []byte("/Users/")) || bytes.Contains(data, []byte("C:\\Users\\")) || email.Match(data) {
			return fmt.Errorf("personal identifier or local path found in %s", name)
		}
		if bytes.Contains(data, []byte("-----BEGIN PRIVATE KEY-----")) || bytes.Contains(data, []byte("-----BEGIN RSA PRIVATE KEY-----")) {
			return fmt.Errorf("private key found in %s", name)
		}
		for _, secret := range private {
			if bytes.Contains(data, secret) {
				return fmt.Errorf("local configuration value found in %s", name)
			}
		}
	}
	return nil
}
func writeArchive(output, edition string, e *exporter) (string, error) {
	names := make([]string, 0, len(e.files))
	for name := range e.files {
		names = append(names, name)
	}
	sort.Strings(names)
	var manifest strings.Builder
	for _, name := range names {
		digest := sha256.Sum256(e.files[name])
		fmt.Fprintf(&manifest, "%x  %s\n", digest, name)
	}
	e.files["SOURCE-SHA256SUMS"] = []byte(manifest.String())
	names = append(names, "SOURCE-SHA256SUMS")
	sort.Strings(names)
	var archive bytes.Buffer
	zip := gzip.NewWriter(&archive)
	zip.Header.ModTime = time.Unix(0, 0)
	writer := tar.NewWriter(zip)
	for _, name := range names {
		mode := int64(0644)
		if e.executable[name] {
			mode = 0755
		}
		data := e.files[name]
		header := &tar.Header{Name: "semi-vix-" + edition + "/" + name, Mode: mode, Size: int64(len(data)), ModTime: time.Unix(0, 0), Typeflag: tar.TypeReg, Format: tar.FormatPAX}
		if err := writer.WriteHeader(header); err != nil {
			return "", err
		}
		if _, err := writer.Write(data); err != nil {
			return "", err
		}
	}
	if err := writer.Close(); err != nil {
		return "", err
	}
	if err := zip.Close(); err != nil {
		return "", err
	}
	name := "semi-vix-" + edition + "-source.tar.gz"
	if err := os.WriteFile(filepath.Join(output, name), archive.Bytes(), 0644); err != nil {
		return "", err
	}
	digest := sha256.Sum256(archive.Bytes())
	return hex.EncodeToString(digest[:]) + "  " + name + "\n", nil
}
func export(root, output, edition string) (string, error) {
	e := &exporter{root: root, files: map[string][]byte{}, executable: map[string]bool{"build.sh": true, "docker/entrypoint.sh": true, "init-env.sh": true}}
	for _, name := range []string{"go.mod", "go.sum", ".dockerignore", ".gitignore", "docker/nginx.conf", "docker/entrypoint.sh", "scripts/init-env.sh"} {
		target := name
		if name == "scripts/init-env.sh" {
			target = "init-env.sh"
		}
		if err := e.add(name, target); err != nil {
			return "", err
		}
	}
	if err := e.tree("go", map[string]bool{".go": true, ".sql": true, ".csv": true}); err != nil {
		return "", err
	}
	if err := e.tree("frontend/src", map[string]bool{".ts": true, ".tsx": true, ".css": true, ".svg": true}); err != nil {
		return "", err
	}
	for _, name := range []string{"package.json", "package-lock.json", "index.html", "vite.config.ts", "tsconfig.json", "tsconfig.app.json", "tsconfig.node.json"} {
		if err := e.add("frontend/"+name, "frontend/"+name); err != nil {
			return "", err
		}
	}
	dockerfile := "Dockerfile.alpaca"
	description := "仅支持 Alpaca。应用、认证、计算、调度、数据库迁移与进程管理均使用 Go；镜像不含 Python。"
	if edition == "full" {
		dockerfile = "Dockerfile"
		description = "支持 Alpaca、IBKR 和富途。公共接口、计算、调度、数据库迁移与进程管理使用 Go；Python 仅用于 IBKR／富途 SDK 桥接。"
		for _, name := range []string{"requirements-runtime.txt", "requirements-futu.txt", "docker/sdk-files.txt"} {
			if err := e.add(name, name); err != nil {
				return "", err
			}
		}
		for _, name := range strings.Fields(string(e.files["docker/sdk-files.txt"])) {
			if !strings.HasPrefix(name, "backend/app/") || !strings.HasSuffix(name, ".py") {
				return "", fmt.Errorf("invalid SDK source path: %s", name)
			}
			if err := e.add(name, name); err != nil {
				return "", err
			}
		}
	}
	if err := e.add(dockerfile, "Dockerfile"); err != nil {
		return "", err
	}
	compose, err := os.ReadFile(filepath.Join(root, "docker-compose.yml"))
	if err != nil {
		return "", err
	}
	text := strings.ReplaceAll(string(compose), "${SVIX_DOCKERFILE:-Dockerfile}", "Dockerfile")
	text = strings.ReplaceAll(text, "${SVIX_IMAGE:-semi-vix-platform:latest}", "${SVIX_IMAGE:-semi-vix-platform:"+edition+"}")
	if edition == "alpaca" {
		text = regexp.MustCompile(`(?m)^.*PIP_INDEX_URL.*\n`).ReplaceAllString(text, "")
	}
	e.files["docker-compose.yml"] = []byte(text)
	env, err := os.ReadFile(filepath.Join(root, ".env.example"))
	if err != nil {
		return "", err
	}
	text = string(env)
	if edition == "alpaca" {
		text = regexp.MustCompile(`(?m)^(?:IBKR_|FUTU_|PIP_INDEX_URL|SVIX_DOCKERFILE|SVIX_IMAGE).*\n`).ReplaceAllString(text, "")
	}
	e.files[".env.example"] = []byte(text)
	e.files["build.sh"] = []byte("#!/usr/bin/env sh\nset -eu\ncd \"$(dirname \"$0\")\"\ndocker build \"$@\" -t semi-vix-platform:" + edition + " .\n")
	e.files["README.md"] = []byte("# Semi-VIX " + edition + " 源码版\n\n" + description + "\n\n源码包不含个人配置、账户、密钥、数据库、行情记录或预编译镜像；配置模板仅含占位值。\n\n## 编译与启动\n\n需要 Docker Compose。不指定 CPU 架构时使用构建机器的架构；可通过 Docker 的 `--platform` 参数选择平台。\n\n```sh\n./init-env.sh\n./build.sh\ndocker compose up -d --no-build\ndocker compose port app 80\n```\n\n`init-env.sh` 会在本机生成随机密钥和密码，请保管 `.env`。首次登录需要绑定 TOTP。行情凭据在面板中配置。\n\n例如为另一台机器编译：\n\n```sh\n./build.sh --platform linux/arm64\n# 或 ./build.sh --platform linux/amd64\n```\n\n镜像平台应与部署机器一致。完整 SDK 版还需对应平台的上游 SDK 依赖；IB Gateway/TWS 和 Futu OpenD 在外部运行。\n\n## 更新\n\n先备份数据库，然后加载或编译新镜像，执行 `docker compose up -d --no-build`。保留原 `.env`、Compose 项目名称和数据库卷；不删除数据卷。两版共用 PostgreSQL 16 表结构和迁移版本标记。从完整版切换到 Alpaca 版后需在设置中启用 Alpaca；其他提供商凭据保留但不会调用。\n\n## 验证\n\n`go test ./go/...` 运行 Go 单元测试。Docker 编译会执行相同测试并编译前端。`SOURCE-SHA256SUMS` 列出源码文件的校验和。\n")
	if err := audit(e.files, credentials(root), edition); err != nil {
		return "", err
	}
	e.files["PRIVACY-CHECK.md"] = []byte("# 发布文件检查\n\n按明确文件清单打包；拒绝符号链接。\n\n不包含真实 .env、数据库或备份、证书与私钥、日志、Git 历史、个人说明文档、node_modules、虚拟环境及本机构建产物。\n\n检查了本地配置中的敏感值是否出现在源码中，以及本机用户目录、电子邮箱和私钥内容。配置模板保留占位符；测试代码中的固定值为合成测试数据。\n\n归档文件的所有者、时间戳已归一化，不保留本机文件元信息。本文件不包含检查时读取的个人配置值。\n")
	return writeArchive(output, edition, e)
}
func main() {
	root := flag.String("root", ".", "project source root")
	output := flag.String("output", "releases/source-editions", "local output directory")
	flag.Parse()
	if err := os.MkdirAll(*output, 0755); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	var sums strings.Builder
	for _, edition := range []string{"alpaca", "full"} {
		sum, err := export(*root, *output, edition)
		if err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		sums.WriteString(sum)
	}
	if err := os.WriteFile(filepath.Join(*output, "SHA256SUMS"), []byte(sums.String()), 0644); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	fmt.Print(sums.String())
}

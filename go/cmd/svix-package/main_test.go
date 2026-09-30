package main

import (
	"archive/tar"
	"bytes"
	"compress/gzip"
	"io"
	"os"
	"path/filepath"
	"testing"
)

func TestPrivateContentCannotBeExported(t *testing.T) {
	cases := []map[string][]byte{
		{"go/example.go": []byte("secret-unique-fixture")},
		{"backend/app/bridge.py": []byte("print('fixture')")},
		{"go/example.go": []byte("/Users/private-fixture/project")},
		{"go/example.go": []byte("-----BEGIN PRIVATE KEY-----")},
	}
	for _, files := range cases {
		if err := audit(files, [][]byte{[]byte("secret-unique-fixture")}, "alpaca"); err == nil {
			t.Fatal("private or disallowed content accepted")
		}
	}
	root := t.TempDir()
	if err := os.Mkdir(filepath.Join(root, "go"), 0755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, "outside.go"), []byte("fixture"), 0644); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(filepath.Join(root, "outside.go"), filepath.Join(root, "go", "linked.go")); err != nil {
		t.Fatal(err)
	}
	e := &exporter{root: root, files: map[string][]byte{}}
	if err := e.tree("go", map[string]bool{".go": true}); err == nil {
		t.Fatal("symlink accepted")
	}
}

func TestArchiveDropsLocalMetadataAndIsReproducible(t *testing.T) {
	dir := t.TempDir()
	makeExporter := func() *exporter {
		return &exporter{files: map[string][]byte{"Dockerfile": []byte("FROM fixture"), "build.sh": []byte("#!/bin/sh\n")}, executable: map[string]bool{"build.sh": true}}
	}
	first, err := writeArchive(dir, "alpaca", makeExporter())
	if err != nil {
		t.Fatal(err)
	}
	second, err := writeArchive(dir, "alpaca", makeExporter())
	if err != nil || first != second {
		t.Fatal("non-reproducible archive", err)
	}
	data, err := os.ReadFile(filepath.Join(dir, "semi-vix-alpaca-source.tar.gz"))
	if err != nil {
		t.Fatal(err)
	}
	zip, err := gzip.NewReader(bytes.NewReader(data))
	if err != nil {
		t.Fatal(err)
	}
	defer zip.Close()
	reader := tar.NewReader(zip)
	for {
		header, err := reader.Next()
		if err == io.EOF {
			break
		}
		if err != nil {
			t.Fatal(err)
		}
		if header.Uid != 0 || header.Gid != 0 || header.Uname != "" || header.Gname != "" || header.ModTime.Unix() != 0 {
			t.Fatal("local metadata retained")
		}
	}
}

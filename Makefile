#!/usr/bin/make -f
# -*- makefile -*-
# ex: set tabstop=4 noexpandtab:
# -*- coding: utf-8 -*

default: help

jq?=jq --indent 4

help: README.md
	@echo "Please read $^"
	@echo ""
	@head $^
	@echo ""
	@echo "More details in $^"

setup:
	@echo "info: $@: Checking presence of tools if not please install them"
	${jq} --version

lint: setup
	@echo "info: $@: json files"
	find . \
		-iname "*_cache" -type d -prune -false \
		-o -iname "*.json" -type f \
		-print \
	| while read file ; do \
		${jq} . "$${file}" > "$${file}.tmp" && mv "$${file}.tmp" "$${file}" ; \
	done

check: lint
	@echo "info: $@: will pass if sources are linted, if not please lint and commit"
	git diff --stat --exit-code

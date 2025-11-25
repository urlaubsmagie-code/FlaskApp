#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test to verify Jinja2 template syntax is valid
"""

from jinja2 import Environment, FileSystemLoader
import os

template_dir = "templates"
template_file = "index.html"

try:
    env = Environment(loader=FileSystemLoader(template_dir))
    template = env.get_template(template_file)
    print(f"✅ Template '{template_file}' is valid!")
    print(f"   Variables used: {template.module.__dict__.keys()}")
except Exception as e:
    print(f"❌ Template Error in '{template_file}':")
    print(f"   {e}")

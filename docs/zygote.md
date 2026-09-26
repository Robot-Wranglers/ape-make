# The Zygote

## Overview

### Why parse once

### What a request is

## Two roles on one binary

### Serve

### Client

### Selection by argv

## Lifecycle of a request

### Connect

### What the request carries

### Fork and the fresh copy

### The reply

## Refusal and fallback

### Options the zygote does not hold

### The cold command

### A missing socket

## Environment

### Handoff from a loader

### Rearming parse-time values

## Recursion

### Routing by path

### Depth and parse cost

## Signals and the terminal

### A signalled client

### Interrupts and reaping

### Foreground jobs under a served request

## State shared with the parent

### Files and intermediates

### Persistent guest state across requests

### Init and hooks in the zygote

## Streams and descriptors

### Passing the three descriptors

### Platform layout of the control message

## Limits

## Demos

## Reference

### Command line

### Reply protocol

### Exit statuses

### Environment variables

### Related patches and tests

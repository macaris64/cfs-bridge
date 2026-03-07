# NASA cFS & Python CCSDS Bridge

High-Fidelity Spacecraft Software Integration Project

## 🎯 Overview

This project establishes a bidirectional communication bridge between NASA’s Core Flight System (cFS) and a Python-based Ground Station application. The core objective is to demonstrate how a modern high-level language can interact with flight-critical software using the industry-standard CCSDS (Consultative Committee for Space Data Systems) Space Packet Protocol.

## 🏗️ System Architecture

1. On-Board Segment (NASA cFS):

- Runs within a Linux-based Docker container.

- Utilizes the Software Bus (SB) for internal message routing.

- A custom C-module acts as the "Ingest/Egress" point for external UDP traffic.

2. Ground Segment (Python App):

- A lightweight Python application responsible for telemetry visualization and command generation.

- Uses the struct library to perform binary serialization of CCSDS headers.

3. Transport Layer:

- Protocol: UDP (User Datagram Protocol).

- Data Format: CCSDS Space Packet (Primary Header + Payload).

## 📡 Technical Specifications

### The CCSDS Bridge

The communication relies on the CCSDS Space Packet Protocol. Every packet sent from Python to cFS includes a 6-byte primary header:

- APID (Application Process Identifier): Routes the packet to the correct cFS application.

- Sequence Count: Tracks packet continuity.

- Packet Length: Defines the size of the telemetry or command data.

### Network Configuration

| Service       | Port | Protocol |Description|
|---------------|------|-----|-----------|
| cFS Command   | 1234 | UDP | Commands sent from Python -> cFS |
| cFS Telemetry | 2234 | UDP | Data sent from cFS -> Python     |

### 🛠️ Tech Stack

- Core: NASA cFS (Core Flight Executive, OSAL, PSP).
- Language: C (Flight Software) & Python 3.10+ (Ground Station).
- DevOps: Docker & Docker Compose for orchestration.
- Communication: BSD Sockets & CCSDS Standards.

### 🚀 Key Goals

- [ ] Containerization: Successfully compile and run cFS inside a Docker environment.

- [ ] Binary Packing: Build a Python utility to generate valid 48-bit CCSDS headers.

- [ ] Software Bus Integration: Verify that a packet sent from Python is received and logged by the cFS TO_LAB or SAMPLE_APP.

- [ ] Telemetry Feedback: Receive a "Heartbeat" packet from cFS and parse it in the Python console.

---

Developed as a weekend engineering project to explore the intersection of Aerospace Engineering and Modern Software Development.

---
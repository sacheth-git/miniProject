"""Generate synthetic sample resumes (no real people) as PDFs.

Writes backend/data/samples/*.pdf. Two of the five use a two-column layout.
Usage (from backend/): .\\.venv\\Scripts\\python.exe scripts\\make_sample_resumes.py
"""

from __future__ import annotations

from pathlib import Path

import fitz

OUT = Path(__file__).resolve().parents[1] / "data" / "samples"
CSS = """
* { font-family: sans-serif; font-size: 9.5pt; line-height: 1.3; }
h1 { font-size: 18pt; margin: 0 0 2pt 0; }
h2 { font-size: 11pt; margin: 9pt 0 3pt 0; border-bottom: 1px solid #888; }
p, li { margin: 0 0 2pt 0; }
ul { margin: 0 0 0 12pt; padding: 0; }
.muted { color: #444; }
"""

RESUMES: dict[str, dict[str, str]] = {
    "uday_ml.pdf": {
        "layout": "single",
        "body": """
<h1>Uday Kiran Rao</h1>
<p class="muted">uday.rao.demo@example.com | +91 98450 12345 | Bengaluru, India | github.com/uday-demo</p>
<h2>Summary</h2>
<p>Final-year B.Tech student focused on machine learning and computer vision, with internship experience building NLP models.</p>
<h2>Technical Skills</h2>
<p>Languages: Python, SQL, C++</p>
<p>ML/DL: Machine Learning, Deep Learning, TensorFlow, PyTorch, scikit-learn, OpenCV, NLP</p>
<p>Tools: Git, Docker, Jupyter, Pandas, NumPy, Flask</p>
<h2>Experience</h2>
<p><b>Machine Learning Intern</b>, Nimbus Analytics Pvt Ltd, Bengaluru (Jun 2024 - Dec 2024)</p>
<ul>
<li>Developed a text classification model with BERT and Hugging Face for customer support tickets, reaching 91% F1.</li>
<li>Wrote SQL queries over PostgreSQL to build training datasets and automated reports.</li>
<li>Packaged the model as a REST API with Flask and deployed it in Docker containers.</li>
</ul>
<h2>Projects</h2>
<ul>
<li><b>Helmet detection</b>: real-time object detection with YOLO and OpenCV on traffic camera video.</li>
<li><b>Resume ranker</b>: sentence embeddings and cosine similarity to rank resumes against job descriptions.</li>
</ul>
<h2>Education</h2>
<p>B.Tech in Computer Science and Engineering, Sahyadri Institute of Technology, Mangaluru (2021 - 2025), CGPA 8.6</p>
<h2>Certifications</h2>
<p>Deep Learning Specialization (online course)</p>
""",
    },
    "priya_fullstack.pdf": {
        "layout": "two",
        "left": """
<h1>Priya Nair</h1>
<p class="muted">priya.nair.demo@example.com</p>
<p class="muted">+91 90000 11122</p>
<p class="muted">Kochi, India</p>
<h2>Skills</h2>
<p>JavaScript, TypeScript, React, Node.js, Express.js, MongoDB, PostgreSQL, HTML, CSS, Tailwind CSS, Redux, Git, AWS, Jest</p>
<h2>Education</h2>
<p>B.E. in Information Technology</p>
<p>Coastal College of Engineering, Kochi</p>
<p>2019 - 2023</p>
<h2>Certifications</h2>
<p>AWS Certified Cloud Practitioner</p>
""",
        "right": """
<h2>Profile</h2>
<p>Full stack developer with two years of experience building web applications and REST APIs.</p>
<h2>Work Experience</h2>
<p><b>Software Engineer</b>, BrightCart Commerce (Jul 2023 - Present)</p>
<ul>
<li>Built React and TypeScript dashboards used by 300 merchants.</li>
<li>Designed REST APIs with Node.js and Express.js backed by MongoDB.</li>
<li>Set up CI/CD with GitHub Actions and wrote unit tests with Jest.</li>
</ul>
<p><b>Web Development Intern</b>, PixelForge Studio (Jan 2023 - Jun 2023)</p>
<ul>
<li>Converted Figma designs into responsive pages with HTML, CSS and Tailwind CSS.</li>
</ul>
<h2>Projects</h2>
<ul>
<li><b>Event booking app</b>: MERN stack app with JWT authentication and payment integration.</li>
<li><b>Chat service</b>: real-time messaging with WebSockets and Redis.</li>
</ul>
""",
    },
    "arjun_ece.pdf": {
        "layout": "single",
        "body": """
<h1>Arjun Shetty</h1>
<p class="muted">arjun.shetty.demo@example.com | 9876501234 | Mysuru</p>
<h2>Career Objective</h2>
<p>Electronics and communication graduate seeking an embedded systems role.</p>
<h2>Key Skills</h2>
<ul>
<li>Embedded C, C, Python, MATLAB, Verilog</li>
<li>Microcontrollers: Arduino, STM32, ESP32, Raspberry Pi</li>
<li>Protocols: I2C, SPI, UART, CAN Bus</li>
<li>Tools: Proteus, Xilinx Vivado, KiCad, Keil</li>
</ul>
<h2>Internship</h2>
<p><b>Embedded Intern</b>, VoltEdge Systems (May 2024 - Aug 2024)</p>
<ul>
<li>Wrote firmware in Embedded C for an STM32 board reading temperature sensors over I2C.</li>
<li>Ported a FreeRTOS task scheduler and debugged with an oscilloscope.</li>
</ul>
<h2>Academic Projects</h2>
<ul>
<li><b>Smart irrigation</b>: IoT system with ESP32 and soil moisture sensors sending data to Firebase.</li>
<li><b>FIR filter on FPGA</b>: digital signal processing filter designed in Verilog and simulated in ModelSim.</li>
</ul>
<h2>Education</h2>
<p>B.E. in Electronics and Communication, Kaveri Engineering College, Mysuru (2020 - 2024), CGPA 7.9</p>
<p>12th (PUC), 2020, 88%</p>
""",
    },
    "meera_data.pdf": {
        "layout": "two",
        "left": """
<h1>Meera Iyer</h1>
<p class="muted">meera.iyer.demo@example.com</p>
<p class="muted">+91 81234 56789</p>
<p class="muted">Chennai</p>
<h2>Technical Skills</h2>
<ul>
<li>Python</li>
<li>SQL</li>
<li>R</li>
<li>Power BI</li>
<li>Tableau</li>
<li>Advanced Excel</li>
<li>Pandas</li>
<li>Statistics</li>
</ul>
<h2>Education</h2>
<p>M.Sc. in Statistics</p>
<p>Lakeview University, Chennai</p>
<p>2020 - 2022</p>
""",
        "right": """
<h2>Professional Summary</h2>
<p>Data analyst with experience in business intelligence, dashboards and A/B testing for consumer products.</p>
<h2>Experience</h2>
<p><b>Data Analyst</b>, Saffron Retail Analytics (Aug 2022 - Present)</p>
<ul>
<li>Built Power BI dashboards tracking weekly sales KPIs across 40 stores.</li>
<li>Ran A/B testing on pricing experiments and reported results to product managers.</li>
<li>Automated data cleaning in Python with Pandas, cutting report time by 60%.</li>
</ul>
<p><b>Analytics Intern</b>, GreenLeaf Foods (Jan 2022 - Jun 2022)</p>
<ul>
<li>Performed exploratory data analysis and time series forecasting of demand.</li>
</ul>
<h2>Projects</h2>
<ul>
<li><b>Churn analysis</b>: logistic regression in R on telecom customer data.</li>
</ul>
""",
    },
    "rahul_mech.pdf": {
        "layout": "single",
        "body": """
<h1>Rahul Deshpande</h1>
<p class="muted">rahul.d.demo@example.com | +91 77000 33445 | Pune</p>
<h2>Summary</h2>
<p>Mechanical engineer interested in product design and simulation.</p>
<h2>Skills</h2>
<p>SolidWorks, AutoCAD, CATIA, ANSYS, MATLAB, GD&amp;T, Finite Element Analysis, CNC Programming, Six Sigma</p>
<h2>Experience</h2>
<p><b>Graduate Engineer Trainee</b>, Sahyadri Auto Components (Jul 2023 - Jun 2024)</p>
<ul>
<li>Created 3D models and drawings of brackets in SolidWorks following GD&amp;T standards.</li>
<li>Ran structural analysis in ANSYS to reduce part weight by 12%.</li>
<li>Supported lean manufacturing initiatives on the machining line.</li>
</ul>
<h2>Projects</h2>
<ul>
<li><b>Heat exchanger study</b>: computational fluid dynamics simulation of a shell and tube heat exchanger.</li>
</ul>
<h2>Education</h2>
<p>B.Tech in Mechanical Engineering, Deccan Institute of Technology, Pune (2019 - 2023)</p>
""",
    },
}


def _html(body: str) -> str:
    return f"<html><body>{body}</body></html>"


def build(name: str, spec: dict[str, str]) -> Path:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    margin = 36
    if spec["layout"] == "single":
        page.insert_htmlbox(fitz.Rect(margin, margin, 595 - margin, 842 - margin), _html(spec["body"]), css=CSS)
    else:
        split = 215
        page.insert_htmlbox(fitz.Rect(margin, margin, split - 10, 842 - margin), _html(spec["left"]), css=CSS)
        page.insert_htmlbox(fitz.Rect(split + 10, margin, 595 - margin, 842 - margin), _html(spec["right"]), css=CSS)
    path = OUT / name
    doc.save(path)
    doc.close()
    return path


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, spec in RESUMES.items():
        print("wrote", build(name, spec))


if __name__ == "__main__":
    main()

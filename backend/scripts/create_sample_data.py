"""
Sample Data Generator

Creates synthetic PDF documents for testing the PIA pipeline.
Run this to generate sample interview experiences, JDs, and aptitude material.

Usage:
    python -m backend.scripts.create_sample_data
"""

import os
from pathlib import Path

# We'll create text files that can be used for testing
# For actual PDFs, you'd need reportlab or fpdf, but for the pipeline
# we can also support .txt files or create minimal PDFs with pymupdf

SAMPLE_DATA = {
    "interview_experiences": {
        "Amazon.pdf": """AMAZON INTERVIEW EXPERIENCE - SDE-1
Campus Placement 2024

COMPANY OVERVIEW:
Company: Amazon
Role: SDE-1 (Software Development Engineer)
Package: 28-32 LPA (Base + Stocks + Bonus)
Eligibility: 7+ CGPA, CSE/IT/ECE branches, No active backlogs

ONLINE ASSESSMENT (Round 1):
Platform: Amazon proprietary portal (HackerRank based)
Duration: 90 minutes
- 2 Coding Questions (DSA focused):
  1. Given an array, find two numbers that add up to a target sum (Two Sum problem) - Medium difficulty
  2. Design a function to find the longest palindromic substring in a given string - Medium difficulty
- Work Simulation (Behavioral scenarios - Leadership Principles based)

TECHNICAL INTERVIEW - ROUND 1:
Duration: 60 minutes
Questions:
- Explain the difference between ArrayList and LinkedList in Java. When would you use each?
- Design a LRU Cache with O(1) get and put operations. Write the complete code.
- What is the time complexity of different sorting algorithms? Compare QuickSort and MergeSort.
- Implement Binary Search on a rotated sorted array.
- Explain how HashMap works internally in Java.
Topics: DSA, Data Structures, System Design basics

TECHNICAL INTERVIEW - ROUND 2:
Duration: 60 minutes
Questions:
- Design a URL shortener system. Discuss database schema, API design, and scaling.
- What is the difference between process and thread?
- Explain REST API principles. What makes an API RESTful?
- Given a binary tree, find the lowest common ancestor of two nodes.
- Discuss database indexing. When would you use B-tree vs Hash index?
Topics: System Design, OS, DBMS, DSA

HR / BAR RAISER ROUND:
Duration: 45 minutes
Questions:
- Tell me about a time you disagreed with a team member (Leadership Principle: Have Backbone)
- Describe a situation where you had to meet a tight deadline
- Why Amazon? What do you know about our Leadership Principles?
- Where do you see yourself in 5 years?
- Tell me about a project you're most proud of.

TIPS:
- Practice at least 150+ LeetCode problems (focus on Medium difficulty)
- Study Amazon Leadership Principles thoroughly
- Practice system design for 2-3 common scenarios
- Time management is crucial in OA
""",
        "Infosys.pdf": """INFOSYS INTERVIEW EXPERIENCE
Campus Placement 2024

COMPANY OVERVIEW:
Company: Infosys
Roles: Systems Engineer (SE), Digital Specialist Engineer (DSE), Power Programmer (PP)
Package: SE - 3.6 LPA, DSE - 6.5 LPA, PP - 8 LPA
Eligibility: Minimum 60% throughout academics (10th, 12th, UG), No active backlogs, All branches eligible for SE

ONLINE ASSESSMENT (Round 1):
Platform: Infosys proprietary portal
Duration: 3 hours
Sections:
- Quantitative Aptitude (20 questions, 30 minutes): Percentages, Profit & Loss, Time & Work, Probability
- Logical Reasoning (20 questions, 25 minutes): Puzzles, Seating Arrangement, Blood Relations, Coding-Decoding
- Verbal Ability (20 questions, 20 minutes): Reading Comprehension, Error Spotting, Sentence Completion
- Programming MCQs (10 questions, 15 minutes): C/Java basics, Output prediction
- Coding (2 questions, 40 minutes): Basic array manipulation, String operations

TECHNICAL INTERVIEW (Round 2):
Duration: 30-45 minutes
Questions:
- What is Object-Oriented Programming? Explain its four pillars with examples.
- What is the difference between a stack and a queue? Give real-world examples.
- Write a SQL query to find the second highest salary from an Employee table.
- What is normalization? Explain 1NF, 2NF, 3NF with examples.
- What is the difference between INNER JOIN and LEFT JOIN?
- Explain the concept of recursion with an example.
- What is a linked list? How is it different from an array?
- What are the different types of testing in software development?
Topics: OOP, SQL, DBMS, Data Structures, Software Engineering basics

HR INTERVIEW (Round 3):
Duration: 15-20 minutes
Questions:
- Tell me about yourself.
- Why Infosys? What do you know about the company?
- What are your strengths and weaknesses?
- Where do you see yourself in 5 years?
- Are you willing to relocate to any city in India?
- Do you have any questions for us?

TIPS:
- Infosys focuses more on aptitude than coding
- Brush up on OOP concepts and basic SQL
- Be confident and clear in HR round
- Practice aptitude daily for at least 2 weeks before the test
""",
        "ProcDNA.pdf": """PROCDNA INTERVIEW EXPERIENCE
Campus Placement 2024

COMPANY OVERVIEW:
Company: ProcDNA
Role: Associate Analyst
Package: 16 LPA
Eligibility: 7+ CGPA, CSE/IT/Data Science branches

ONLINE ASSESSMENT (Round 1):
Platform: HackerEarth
Duration: 90 minutes
Sections:
- SQL Queries (5 questions, 40 minutes):
  1. Write a query to find employees earning more than the average salary in their department.
  2. Use GROUP BY and HAVING to find departments with more than 5 employees.
  3. Write a query using window functions (RANK, ROW_NUMBER) to rank employees by salary.
  4. Subquery vs CTE - Write the same query using both approaches.
  5. Find duplicate records in a table using GROUP BY.

- Python MCQs (10 questions, 20 minutes):
  Topics: List comprehensions, Decorators, Generators, Exception handling, OOP in Python

- Statistics MCQs (10 questions, 30 minutes):
  Topics: Mean, Median, Mode, Standard Deviation, Probability distributions, Hypothesis testing

TECHNICAL INTERVIEW - ROUND 1 (SQL & Database Focus):
Duration: 45 minutes
Questions:
- What is the difference between INNER JOIN and LEFT JOIN? Write examples for each.
- Explain GROUP BY vs HAVING clause. When would you use each?
- What is normalization? Explain up to 3NF with examples.
- Write a SQL query to find the top 3 highest-paid employees in each department.
- What are indexes in databases? How do they improve query performance?
- Explain the difference between clustered and non-clustered indexes.
- What is a stored procedure? When would you use one?
Topics: SQL, DBMS, Database Design

TECHNICAL INTERVIEW - ROUND 2 (Python & Statistics Focus):
Duration: 45 minutes
Questions:
- What is the difference between a list and a tuple in Python?
- Explain decorators in Python. Write a simple decorator.
- What is the difference between deep copy and shallow copy?
- What are generators in Python? How do they differ from regular functions?
- Explain exception handling in Python with try-except-finally.
- What is hypothesis testing? Explain null and alternative hypothesis.
- Explain p-value. What does a p-value of 0.03 mean?
- What is the Central Limit Theorem?
- Explain the difference between Type I and Type II errors.
Topics: Python, Statistics, Probability

HR INTERVIEW (Round 3):
Duration: 20 minutes
Questions:
- Tell me about yourself.
- Why ProcDNA? What interests you about data analytics?
- Describe a challenging project you've worked on.
- How do you handle pressure and tight deadlines?
- Do you have any questions about the role or company?

TIPS:
- SQL is the most important skill for ProcDNA - practice complex queries
- Brush up on Python fundamentals, not just syntax but concepts
- Statistics knowledge is tested in detail - don't skip probability
- Data visualization questions might come up - know basic chart types
- Company values data-driven decision making - emphasize analytical projects
""",
        "Walmart.pdf": """WALMART INTERVIEW EXPERIENCE
Campus Placement 2024

COMPANY OVERVIEW:
Company: Walmart (Walmart Global Tech)
Role: Software Development Engineer (SDE)
Package: 25-30 LPA
Eligibility: 7.5+ CGPA, CSE/IT branches, No backlogs

ONLINE ASSESSMENT (Round 1):
Platform: HackerRank
Duration: 75 minutes
- 3 Coding Questions:
  1. Binary Search on a sorted rotated array - Find the minimum element (Medium)
  2. Two pointer technique: Given a sorted array, find pair with given sum (Easy)
  3. Linked list: Detect and remove cycle in a linked list (Medium-Hard)
- MCQs on DSA and SQL (15 questions)
  - Time complexity questions
  - SQL JOIN types and aggregations
  - Tree traversal order questions

TECHNICAL INTERVIEW - ROUND 1 (DSA Focus):
Duration: 60 minutes
Questions:
- Implement BFS and DFS for a graph. Discuss time and space complexity.
- Reverse a linked list iteratively and recursively. Analyze both approaches.
- Given a binary search tree, find the kth smallest element.
- Explain different types of balanced BSTs (AVL, Red-Black trees).
- Solve: Given a matrix, find the longest increasing path. Discuss approach before coding.
- What is dynamic programming? Solve the coin change problem.
Topics: DSA (Arrays, Trees, Graphs, LinkedList, DP)

TECHNICAL INTERVIEW - ROUND 2 (System Design + SQL):
Duration: 60 minutes
Questions:
- Design a URL shortener like bit.ly. Discuss:
  - Database schema
  - Hash function selection
  - Handling collisions
  - Scaling to millions of requests
  - Caching strategy (Redis/Memcached)
- Explain different types of SQL JOINs with examples.
- Write a SQL query to find the most purchased product in each category.
- What is database sharding? When would you use it?
- Explain the CAP theorem. Give examples of CP and AP systems.
- What is load balancing? Compare different algorithms (Round Robin, Least Connections).
Topics: System Design, SQL, Distributed Systems

TECHNICAL INTERVIEW - ROUND 3 (Behavioral + Technical Mix):
Duration: 45 minutes
Questions:
- Tell me about a project where you used data structures effectively.
- How would you design an API rate limiter?
- What is containerization? Have you used Docker?
- Explain microservices vs monolithic architecture.
- Describe a time you optimized code for better performance.
Topics: System Design, DevOps, Behavioral

HR ROUND:
Duration: 20 minutes
Questions:
- Why Walmart?
- Tell me about yourself.
- What's your biggest technical achievement?
- How do you stay updated with technology trends?
- Salary expectations and joining timeline.

TIPS:
- Walmart focuses heavily on DSA - solve 200+ LeetCode problems
- System design is critical - study at least 5 common design patterns
- SQL knowledge is essential - practice complex queries with JOINs and subqueries
- They value clean code and communication - explain your approach before coding
- Practice mock interviews for time management
""",
    },
    "job_descriptions": {
        "ProcDNA_JD.pdf": """JOB DESCRIPTION - PROCDNA

Position: Associate Analyst
Company: ProcDNA
Location: Hyderabad, India
Type: Full-time
Package: 16 LPA

ABOUT THE ROLE:
As an Associate Analyst at ProcDNA, you will work with cross-functional teams to analyze large datasets, build data pipelines, and create actionable insights. You will be responsible for designing and maintaining SQL-based reporting systems and building statistical models.

REQUIRED SKILLS:
- SQL: Advanced proficiency required. Experience with complex queries, JOINs, window functions, CTEs, stored procedures
- Python: Proficiency in data analysis libraries (Pandas, NumPy, Matplotlib, Seaborn)
- Statistics: Strong foundation in descriptive and inferential statistics, hypothesis testing, regression analysis
- Data Visualization: Experience with Tableau, Power BI, or similar tools
- Excel: Advanced Excel skills including pivot tables, VLOOKUP, conditional formatting
- Machine Learning: Basic understanding of supervised and unsupervised learning algorithms

NICE TO HAVE:
- Experience with cloud platforms (AWS, GCP, Azure)
- Knowledge of ETL processes and data warehousing
- R programming
- Experience with A/B testing
- Familiarity with Agile methodologies

KEY RESPONSIBILITIES:
- Design and maintain SQL-based reporting and analytics dashboards
- Perform exploratory data analysis on large datasets
- Build and validate statistical models for business forecasting
- Collaborate with stakeholders to translate business requirements into data solutions
- Create data visualizations and presentations for leadership
- Participate in data quality assurance and governance initiatives

ELIGIBILITY:
- Bachelor's or Master's in Computer Science, Data Science, Statistics, or related field
- CGPA 7.0 or above
- Strong analytical and problem-solving skills
- Excellent communication skills
""",
        "Walmart_JD.pdf": """JOB DESCRIPTION - WALMART GLOBAL TECH

Position: Software Development Engineer (SDE)
Company: Walmart Global Tech
Location: Bangalore, India
Type: Full-time
Package: 25-30 LPA

ABOUT THE ROLE:
Join Walmart Global Tech as an SDE to build scalable, high-performance applications that serve millions of customers worldwide. You will work on cutting-edge technologies to solve complex problems in e-commerce, supply chain, and customer experience.

REQUIRED SKILLS:
- Programming: Strong proficiency in Java or Python
- Data Structures and Algorithms: Deep understanding of arrays, trees, graphs, dynamic programming, sorting algorithms
- SQL: Proficiency in writing complex queries, JOINs, aggregations, and optimization
- System Design: Understanding of distributed systems, microservices, API design, caching
- REST APIs: Experience designing and consuming RESTful web services
- Cloud Technologies: Familiarity with AWS/GCP/Azure services
- Version Control: Git proficiency

NICE TO HAVE:
- Experience with containerization (Docker, Kubernetes)
- Knowledge of CI/CD pipelines
- NoSQL databases (MongoDB, Cassandra)
- Message queues (Kafka, RabbitMQ)
- Frontend technologies (React, Angular)
- Experience with large-scale distributed systems

KEY RESPONSIBILITIES:
- Design, develop, and maintain high-quality software solutions
- Write clean, efficient, and well-documented code
- Participate in code reviews and architectural discussions
- Collaborate with product and design teams to define features
- Troubleshoot production issues and implement fixes
- Mentor junior engineers and contribute to team growth

ELIGIBILITY:
- Bachelor's or Master's in Computer Science or related field
- CGPA 7.5 or above
- Strong problem-solving and analytical skills
- Excellent teamwork and communication abilities
""",
    },
    "aptitude_material": {
        "SQL.pdf": """SQL COMPREHENSIVE GUIDE FOR PLACEMENT PREPARATION

1. INTRODUCTION TO SQL
SQL (Structured Query Language) is the standard language for managing relational databases.
Key concepts: DDL, DML, DCL, TCL

2. SELECT STATEMENT
Basic syntax: SELECT columns FROM table WHERE condition
Examples:
- SELECT * FROM employees WHERE salary > 50000;
- SELECT name, department FROM employees ORDER BY salary DESC;

3. JOINs
INNER JOIN: Returns only matching rows from both tables.
  SELECT e.name, d.dept_name FROM employees e INNER JOIN departments d ON e.dept_id = d.id;

LEFT JOIN: Returns all rows from the left table and matching rows from the right table, with NULLs where there is no match.
  SELECT e.name, d.dept_name FROM employees e LEFT JOIN departments d ON e.dept_id = d.id;

RIGHT JOIN: Opposite of LEFT JOIN - returns all rows from the right table.
FULL OUTER JOIN: Returns all rows from both tables.
CROSS JOIN: Cartesian product of both tables.
SELF JOIN: Joining a table with itself.

4. GROUP BY AND HAVING
GROUP BY: Groups rows that have the same values in specified columns into summary rows. Commonly used with aggregate functions COUNT, SUM, AVG, MAX, MIN.
  SELECT department, COUNT(*) as emp_count FROM employees GROUP BY department;

HAVING: Filters groups after GROUP BY (WHERE filters rows before grouping).
  SELECT department, AVG(salary) as avg_sal FROM employees GROUP BY department HAVING AVG(salary) > 60000;

5. SUBQUERIES AND CTEs
Subquery: A query nested inside another query.
  SELECT name FROM employees WHERE salary > (SELECT AVG(salary) FROM employees);

CTE (Common Table Expression): Named temporary result set.
  WITH high_earners AS (SELECT * FROM employees WHERE salary > 80000)
  SELECT department, COUNT(*) FROM high_earners GROUP BY department;

6. WINDOW FUNCTIONS
ROW_NUMBER(): Assigns unique sequential numbers.
RANK(): Assigns rank with gaps for ties.
DENSE_RANK(): Assigns rank without gaps.
  SELECT name, salary, RANK() OVER (ORDER BY salary DESC) as salary_rank FROM employees;

7. NORMALIZATION
1NF: Each cell contains a single value, no repeating groups.
2NF: In 1NF + all non-key attributes fully dependent on the primary key.
3NF: In 2NF + no transitive dependencies.

8. INDEXES
Indexes speed up data retrieval but slow down INSERT/UPDATE/DELETE.
B-tree index: Default, good for range queries.
Hash index: Good for equality comparisons.
Composite index: Index on multiple columns.
When to use: Frequently queried columns, JOIN columns, WHERE clause columns.
When not to use: Small tables, frequently updated columns, low cardinality columns.
""",
        "DSA.pdf": """DATA STRUCTURES AND ALGORITHMS - PLACEMENT PREPARATION GUIDE

1. ARRAYS
- Contiguous memory allocation
- O(1) access by index, O(n) insertion/deletion
- Common problems: Two Sum, Maximum Subarray (Kadane's algorithm), Rotate Array
- Binary Search on sorted arrays: O(log n) time complexity

2. LINKED LISTS
- Dynamic memory allocation, nodes connected by pointers
- Types: Singly linked, Doubly linked, Circular
- Operations: Insert (O(1) at head), Delete (O(1) if node known), Search (O(n))
- Common problems: Reverse linked list, Detect cycle (Floyd's algorithm), Merge two sorted lists

3. STACKS AND QUEUES
Stack: LIFO (Last In First Out). Operations: push, pop, peek. All O(1).
  Real-world: Browser back button, undo operations, function call stack
Queue: FIFO (First In First Out). Operations: enqueue, dequeue. All O(1).
  Real-world: Print queue, BFS traversal, task scheduling
Priority Queue: Elements have priority, highest priority served first. Implementation: Heap.

4. TREES
Binary Tree: Each node has at most 2 children
Binary Search Tree (BST): Left child < parent < right child
  Search, Insert, Delete: O(h) where h is height
  Inorder traversal gives sorted output
AVL Tree: Self-balancing BST, height difference ≤ 1
  Rotations: Left, Right, Left-Right, Right-Left

5. GRAPHS
Representations: Adjacency Matrix (O(V²) space), Adjacency List (O(V+E) space)
BFS (Breadth-First Search): Uses queue, level-by-level traversal, O(V+E)
  Applications: Shortest path (unweighted), connected components
DFS (Depth-First Search): Uses stack/recursion, O(V+E)
  Applications: Topological sort, cycle detection, connected components

6. SORTING ALGORITHMS
Bubble Sort: O(n²) average and worst
Selection Sort: O(n²) always
Insertion Sort: O(n²) worst, O(n) best (nearly sorted)
Merge Sort: O(n log n) always, stable, O(n) space
QuickSort: O(n log n) average, O(n²) worst. The worst case occurs when the pivot selection is poor (already sorted array with first element as pivot).
Heap Sort: O(n log n) always, in-place

7. DYNAMIC PROGRAMMING
Key idea: Break problem into overlapping subproblems, store solutions.
Approaches: Top-down (memoization) vs Bottom-up (tabulation)
Classic problems:
- Fibonacci: O(n) with DP vs O(2^n) naive recursion
- Coin Change: Given coins and amount, find minimum coins needed
- Longest Common Subsequence: O(m*n) DP solution
- 0/1 Knapsack: O(n*W) where W is capacity

8. BINARY SEARCH
Works on sorted arrays. O(log n) time.
Template:
  left, right = 0, len(arr) - 1
  while left <= right:
      mid = (left + right) // 2
      if arr[mid] == target: return mid
      elif arr[mid] < target: left = mid + 1
      else: right = mid - 1
Variations: Find first/last occurrence, search in rotated array
Asked frequently at: Amazon, Walmart, Google
""",
        "Quant.pdf": """QUANTITATIVE APTITUDE - PLACEMENT PREPARATION GUIDE

1. PERCENTAGES
- Percentage change = ((New - Old) / Old) × 100
- If price increases by x%, to restore: reduce by (100x)/(100+x) %
- Successive percentages: a% and b% = (a + b + ab/100)%

2. PROFIT AND LOSS
- Profit % = (Profit / CP) × 100
- Selling Price = CP × (1 + Profit%/100)
- Discount = Marked Price - Selling Price

3. TIME AND WORK
- If A can do work in x days, A's one day work = 1/x
- A and B together: 1/x + 1/y = 1/T (combined time T)
- Efficiency is inversely proportional to time

4. TIME, SPEED, AND DISTANCE
- Speed = Distance / Time
- Average speed for same distance at speeds a and b = 2ab/(a+b)
- Relative speed: Same direction = |a-b|, Opposite = a+b

5. PROBABILITY
Basic probability = Favorable outcomes / Total outcomes
Key concepts:
- Conditional Probability: P(A|B) = P(A∩B) / P(B)
- Bayes' Theorem: P(A|B) = P(B|A) × P(A) / P(B)
- Independent events: P(A∩B) = P(A) × P(B)
- Expected Value: E(X) = Σ x_i × P(x_i)

6. PERMUTATIONS AND COMBINATIONS
- Permutation (order matters): nPr = n! / (n-r)!
- Combination (order doesn't matter): nCr = n! / (r! × (n-r)!)
- With repetition: n^r (permutation), (n+r-1)Cr (combination)
- Circular permutation: (n-1)!

7. AVERAGES
- Average = Sum / Count
- Weighted average = Σ(value × weight) / Σ(weights)
- If one number is removed/added, new average can be calculated

8. RATIOS AND PROPORTIONS
- If a:b = c:d, then ad = bc (cross multiplication)
- Componendo-Dividendo: (a+b)/(a-b) = (c+d)/(c-d)

9. NUMBER SYSTEMS
- Divisibility rules for 2, 3, 4, 5, 6, 7, 8, 9, 11
- HCF and LCM: HCF × LCM = Product of numbers
- Prime factorization method for HCF/LCM

10. LOGICAL REASONING
- Puzzles and seating arrangements
- Blood relations
- Coding-decoding
- Syllogisms
- Direction sense

TIPS FOR APTITUDE PREPARATION:
- Practice 20-30 problems daily
- Focus on speed and accuracy
- Learn shortcuts for common calculations
- Take timed mock tests regularly
- Infosys, TCS, Wipro focus heavily on aptitude
""",
    },
}


def create_sample_pdfs(data_dir: str = "./data"):
    """Create sample PDF files using pymupdf."""
    try:
        import fitz  # pymupdf
    except ImportError:
        print("pymupdf not installed. Creating text files instead.")
        create_sample_text_files(data_dir)
        return

    data_path = Path(data_dir)

    for category, files in SAMPLE_DATA.items():
        category_dir = data_path / category
        category_dir.mkdir(parents=True, exist_ok=True)

        for filename, content in files.items():
            file_path = category_dir / filename
            if file_path.exists():
                print(f"  Skipping (exists): {file_path}")
                continue

            # Create PDF using pymupdf
            doc = fitz.open()

            # Split content into pages
            lines = content.strip().split("\n")
            current_page_text = ""
            line_count = 0

            for line in lines:
                if len(current_page_text) + len(line) > 2000 or line_count >= 40:
                    # Create new page
                    page = doc.new_page()
                    text_rect = fitz.Rect(50, 50, 545, 792)
                    page.insert_textbox(
                        text_rect,
                        current_page_text,
                        fontsize=10,
                        fontname="helv",
                    )
                    current_page_text = line + "\n"
                    line_count = 1
                else:
                    current_page_text += line + "\n"
                    line_count += 1

            # Last page
            if current_page_text.strip():
                page = doc.new_page()
                text_rect = fitz.Rect(50, 50, 545, 792)
                page.insert_textbox(
                    text_rect,
                    current_page_text,
                    fontsize=10,
                    fontname="helv",
                )

            doc.save(str(file_path))
            doc.close()
            print(f"  Created: {file_path}")

    print(f"\nSample data created in: {data_path}")


def create_sample_text_files(data_dir: str = "./data"):
    """Fallback: create text files if pymupdf not available."""
    data_path = Path(data_dir)

    for category, files in SAMPLE_DATA.items():
        category_dir = data_path / category
        category_dir.mkdir(parents=True, exist_ok=True)

        for filename, content in files.items():
            # Save as .txt instead of .pdf
            txt_name = filename.replace(".pdf", ".txt")
            file_path = category_dir / txt_name
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"  Created: {file_path}")


if __name__ == "__main__":
    print("Creating sample data...")
    create_sample_pdfs()
    print("Done!")

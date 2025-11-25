from flask import Flask, jsonify, render_template, abort
import os
import re
from collections import defaultdict

app = Flask(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

# Regex to pull individual review records out of the escaped JSON
block_pattern = re.compile(
    r'\\"id\\":(?P<id>\d+),'
    r'\\"sourceTable\\":\\"(?P<sourceTable>[^"]+)\\",'
    r'\\"sourceId\\":\\"?(?P<sourceId>[^"\\]+)\\"?,'
    r'\\"rating\\":\\"(?P<rating>bad|fine|good|excellent)\\"'
    r'.*?\\"ratingBucket\\":\\"(?P<ratingBucket>[^"]+)\\"'
    r'.*?\\"ratingScore\\":(?P<ratingScore>-?\d+)'
    r'.*?\\"comment\\":(?P<comment>null|\\".*?\\")'
    r'.*?\\"reviewerId\\":\\"(?P<reviewerId>[^"]+)\\"'
    r'.*?\\"reviewedAt\\":\\"(?P<reviewedAt>[^"]+)\\"'
    r'.*?\\"taskId\\":\\"(?P<taskId>[^"]+)\\"'
    r',\\"taskLabel\\":\\"(?P<taskLabel>[^"]+)\\"',
    re.DOTALL
)

def parse_reviews_for_user(filename: str):
    """Parse one page-source file into a list of review dicts."""
    path = os.path.join(DATA_DIR, filename)
    if not os.path.isfile(path):
        return []

    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    rows = []
    for m in block_pattern.finditer(text):
        g = m.groupdict()
        # Normalize comment field
        comment = g["comment"]
        if comment == "null":
            comment = None
        else:
            # strip the surrounding \"...\"
            comment = comment.strip('\\"')
        rows.append({
            "id": int(g["id"]),
            "sourceTable": g["sourceTable"],
            "sourceId": g["sourceId"],
            "rating": g["rating"],  # bad / fine / good / excellent
            "ratingBucket": g["ratingBucket"],
            "ratingScore": int(g["ratingScore"]),
            "comment": comment,
            "reviewerId": g["reviewerId"],
            "reviewedAt": g["reviewedAt"],
            "taskId": g["taskId"],
            "taskLabel": g["taskLabel"],
        })
    return rows


def list_users():
    """Return list of user names based on files in DATA_DIR."""
    users = []
    if not os.path.isdir(DATA_DIR):
        return users
    for fname in os.listdir(DATA_DIR):
        if fname.lower().endswith(".txt"):
            name = os.path.splitext(fname)[0]
            users.append(name)
    users.sort()
    return users


@app.route("/")
def index():
    # Just serve the HTML shell; JS will call the APIs.
    return render_template("index.html")


@app.route("/api/users")
def api_users():
    """List all users (one per file)."""
    users = list_users()
    return jsonify({"users": users})


@app.route("/api/user/<name>/reviews")
def api_user_reviews(name):
    """Return all raw reviews for a given user (by file name)."""
    filename = f"{name}.txt"
    rows = parse_reviews_for_user(filename)
    if not rows:
        abort(404)
    return jsonify({"name": name, "reviews": rows})


@app.route("/api/user/<name>/summary")
def api_user_summary(name):
    """
    Return pre-aggregated summary for convenience:
      - counts by rating
      - reviewer counts by rating
      - overall counts per reviewer
    """
    filename = f"{name}.txt"
    rows = parse_reviews_for_user(filename)
    if not rows:
        abort(404)

    # Counts by rating
    summary_by_rating = defaultdict(int)
    for r in rows:
        summary_by_rating[r["rating"]] += 1

    # Reviewer counts per rating
    reviewers_by_rating = defaultdict(lambda: defaultdict(int))
    for r in rows:
        reviewers_by_rating[r["rating"]][r["reviewerId"]] += 1

    # Overall per reviewer
    reviewer_totals = defaultdict(lambda: defaultdict(int))
    for r in rows:
        rev = r["reviewerId"]
        reviewer_totals[rev]["total"] += 1
        reviewer_totals[rev][r["rating"]] += 1

    # Make them JSON-friendly
    summary_by_rating = dict(summary_by_rating)
    reviewers_by_rating = {
        rating: [{"reviewerId": rid, "count": cnt}
                 for rid, cnt in sorted(counts.items(), key=lambda x: -x[1])]
        for rating, counts in reviewers_by_rating.items()
    }
    reviewer_totals = [
        {
            "reviewerId": rid,
            "total": info["total"],
            "bad": info.get("bad", 0),
            "fine": info.get("fine", 0),
            "good": info.get("good", 0),
            "excellent": info.get("excellent", 0),
        }
        for rid, info in reviewer_totals.items()
    ]
    reviewer_totals.sort(key=lambda r: -r["total"])

    return jsonify({
        "name": name,
        "summaryByRating": summary_by_rating,
        "reviewersByRating": reviewers_by_rating,
        "reviewerTotals": reviewer_totals,
    })


@app.route("/api/user/<name>/reviews_by_reviewer/<reviewer_id>")
def api_user_reviews_by_reviewer(name, reviewer_id):
    """Return all reviews for this user given by a specific reviewer."""
    filename = f"{name}.txt"
    rows = parse_reviews_for_user(filename)
    if not rows:
        abort(404)

    filtered = [r for r in rows if r["reviewerId"] == reviewer_id]
    return jsonify({
        "name": name,
        "reviewerId": reviewer_id,
        "reviews": filtered,
    })


if __name__ == "__main__":
    os.makedirs(DATA_DIR, exist_ok=True)
    app.run(debug=True)

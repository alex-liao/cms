#!/usr/bin/env python2
# -*- coding: utf-8 -*-

# Programming contest management system
# Copyright © 2010-2012 Giovanni Mascellani <mascellani@poisson.phc.unipi.it>
# Copyright © 2010-2012 Stefano Maggiolo <s.maggiolo@gmail.com>
# Copyright © 2010-2012 Matteo Boscariol <boscarim@hotmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import json

from cms.grading.ScoreType import ScoreTypeAlone


# Dummy function to mark translatable string.
def N_(message):
    return message


class Sum(ScoreTypeAlone):
    """The score of a submission is the sum of the outcomes,
    multiplied by the integer parameter.

    """
    # Mark strings for localization.
    N_("Outcome")
    N_("Details")
    N_("Execution time")
    N_("Memory used")
    N_("N/A")
    TEMPLATE = """\
{% from cms.grading import format_status_text %}
{% from cms.server import format_size %}

{% for tc in details %}
    <b>Outcome: </b>
    {% if "outcome" in tc and "text" in tc %}
    {{ _(tc["outcome"]) }}
    {% else %}
    N/A
    {% end %}
    <br>
    
    <b>Details: </b>
    {% if tc["text"] is not None %}
    {{ format_status_text(tc["text"], _) }}
    {% else %}
    N/A
    {% end %}
    <br>
    
    <b>Execution Time: </b> 
    {% if tc["time"] is not None %}
    {{ _("%(seconds)0.3f s") % {'seconds': tc["time"]} }}
    {% else %}
    N/A
    {% end %}
    <br>
    
    <b>Memory Used: </b> 
    {% if tc["memory"] is not None %}
    {{ format_size(tc["memory"]) }}
    {% else %}
    N/A
    {% end %}
    <br>
    
    {% if "correct_score" in tc %}
    <b>Correction Score: </b> 
    {{ tc["correct_score"] }}
    <br>
    {% end %}
    
    {% if "submission_score" in tc %}
    <b>Submission Score: </b> 
    {{ tc["submission_score"] }}
    <br>
    {% end %}
    
    {% if "execution_score" in tc %}
    <b>Execution Score: </b> 
    {{ tc["execution_score"] }}
    <br>
    {% end %}
    
    
    {% if "estimation_score" in tc %}
    <b>Estimation Score for this submission: </b> 
    {{ tc["estimation_score"] }}
    <br>
    {% end %}
    
    
    
{% end %}"""

    def max_scores(self):
        """Compute the maximum score of a submission.

        returns (float, float): maximum score overall and public.

        """
        public_score = 0.0
        score = 0.0
        for public in self.public_testcases.itervalues():
            if public:
                public_score += self.parameters
            score += self.parameters
        return score, public_score, []

    def compute_score(self, submission_result):
        """Compute the score of a submission.

        See the same method in ScoreType for details.

        """
        # Actually, this means it didn't even compile!
        if not submission_result.evaluated():
            return 0.0, "[]", 0.0, "[]", json.dumps([])

        # XXX Lexicographical order by codename
        indices = sorted(self.public_testcases.keys())
        evaluations = dict((ev.codename, ev)
                           for ev in submission_result.evaluations)
        testcases = []
        public_testcases = []
        score = 0.0
        public_score = 0.0
        
        this_submission = submission_result.submission
        this_task = this_submission.task
        this_contest = this_task.contest
        
        for idx in indices:
            correct_score = float(evaluations[idx].outcome) * 0.6
            this_score = correct_score;
            
            submission_score = 0.3 * (1 - (this_submission.timestamp - this_contest.start).total_seconds() / (this_contest.stop - this_contest.start).total_seconds())
            this_score += submission_score * float(evaluations[idx].outcome)
            execution_score = 0.1 * (1 - evaluations[idx].execution_time / this_task.active_dataset.time_limit);
            this_score += execution_score * float(evaluations[idx].outcome)
            
            tc_outcome = self.get_public_outcome(this_score)
            score += this_score
            testcases.append({
                "idx": idx,
                "outcome": tc_outcome,
                "text": evaluations[idx].text ,
                "time": evaluations[idx].execution_time,
                "memory": evaluations[idx].execution_memory,
                "correct_score": correct_score,
                "submission_score": submission_score,
                "execution_score": execution_score,
                "estimation_score": this_score,
                
                })
            if self.public_testcases[idx]:
                public_score += this_score
                public_testcases.append(testcases[-1])
            else:
                public_testcases.append({"idx": idx})

        return score, json.dumps(testcases), \
            public_score, json.dumps(public_testcases), \
            json.dumps([])

    def get_public_outcome(self, outcome):
        """Return a public outcome from an outcome.

        outcome (float): the outcome of the submission.

        return (float): the public output.

        """
        if outcome < 0.6:
            return N_("Not correct")
        else:
            return N_("Correct")
        
        """if outcome <= 0.0:
            return N_("Not correct")
        elif outcome >= 0.6:
            return N_("Correct")
        else:
            return N_("Partially correct")
        """
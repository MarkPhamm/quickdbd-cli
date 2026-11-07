{% docs average_rating %}
Mean of the category ratings the reviewer actually scored, rounded to 2 decimals. A review that only rated one category is not punished for the rest. Null when no category was scored.
{% enddocs %}

{% docs rating_band %}
average_rating bucketed for reporting: bad (below 2), medium (below 4), good (4 and up), or unknown when average_rating is null.
{% enddocs %}

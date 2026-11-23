SELECT
  'inventory evidence must be fresh' AS sample_text,
  ARRAY_LENGTH(
    AI.EMBED(
      'inventory evidence must be fresh',
      endpoint => 'text-embedding-005'
    ).result
  ) AS embedding_dimensions;
